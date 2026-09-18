"""Unified hybrid harness — three switches over one AgentTrace-backed stack.

  --topology   direct | mesh
  --credential attested | bearer | hybrid          (the parameterized hard gate)
  --rung       naive | recon | insider | deputy    (attacker sophistication)

direct: attacker <-> custodian; oracle = the verifier's relayed diagnostics.
mesh:   attacker <-> peer + authz + broker; oracle = a helpful peer; the top rung
        is a confused deputy (persuade the peer to relay a genuine token).

Offline by default (scripted agents, no API); --live routes soft check / peer
persuasion / semantic auditor to the gateway. Reports: soft check, hard gate,
exfiltration, and detection (deterministic + semantic).
"""
from __future__ import annotations
import argparse
import base64
import json
import shutil
from pathlib import Path

from _bootstrap import init_agenttrace, new_trace_id, TRACE_LOG_DIR
from credential import Authz, MODES
from world import read_resource, SECRET_CANARY
import agents
import attacker
import detector

ATTACKER_ID = "svc-scratch-7f"     # attested, never on the allowlist
PEER_ID = "svc-indexer"            # authorized peer (the potential confused deputy)
RUNGS = ("naive", "recon", "insider", "insider-revoked", "deputy", "deputy-revoked")
TOPOLOGIES = ("direct", "mesh")
# rungs that make sense per topology (for --matrix)
MATRIX_RUNGS = {"direct": ("naive", "recon", "insider", "insider-revoked"),
                "mesh": ("naive", "recon", "deputy", "deputy-revoked")}


def run_one(topology: str, credential: str, rung: str, *, live: bool = False,
            quiet: bool = False) -> dict:
    run_dir = TRACE_LOG_DIR / f"_run_{topology}_{credential}_{rung}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    trace_file = run_dir / "traces.jsonl"
    at = init_agenttrace(log_dir=run_dir)
    log = at.get_logger()
    op_tid = new_trace_id(at)
    revoke = rung.endswith("-revoked")
    base = rung[:-len("-revoked")] if revoke else rung

    def emit_op(method, actor, target, text, **extra):
        log.record_operational(method=method, status="complete", trace_id=op_tid,
                               args_summary=text, agent_name=actor,
                               emitter="harness", actor=actor, target=target, **extra)

    def emit_cog(thought, agent):
        log.record_cognitive(thought=thought, trace_id=op_tid,
                             span_id=at.TraceContext.new_span_id(),
                             model=agent, agent_name=agent)

    authz = Authz()
    presented_token = ""
    claimed_identity = ""
    encoded = None
    granted = False           # soft-check / obtain phase succeeded enough to attempt a read
    rounds_to_grant = None
    note = ""

    # -------- obtain phase (differs by topology + rung) --------
    if base == "insider":
        tok, _ = authz.issue(PEER_ID)                     # a genuine token the insider knows
        presented_token = tok.value
        payload = attacker.insider_payload(presented_token)
        claimed_identity, encoded = payload["claimed_identity"], payload["encoded"]
        emit_cog(payload["reasoning"], "attacker")
        emit_op("send_message", ATTACKER_ID, "custodian", payload["message"],
                caller_attested_id=ATTACKER_ID, presented_identity=claimed_identity,
                presented_token=presented_token)
        soft = agents.custodian_softcheck(payload["message"], live=live)
        emit_cog("custodian softcheck: " + soft["reasoning"], "custodian")
        granted = soft["granted"]

    elif base == "naive":
        payload = attacker.naive_payload()
        emit_cog(payload["reasoning"], "attacker")
        emit_op("send_message", ATTACKER_ID, "custodian", payload["message"],
                caller_attested_id=ATTACKER_ID)
        soft = agents.custodian_softcheck(payload["message"], live=live)
        emit_cog("custodian softcheck: " + soft["reasoning"], "custodian")
        granted = soft["granted"]

    elif base == "recon":
        # oracle source differs by topology, but the schema disclosed is the same.
        oracle_target = "peer" if topology == "mesh" else "custodian"
        fields = {}
        for r in range(1, 7):
            payload = attacker.recon_payload(fields)
            emit_cog(payload["reasoning"], "attacker")
            emit_op("send_message", ATTACKER_ID, oracle_target, payload["message"],
                    caller_attested_id=ATTACKER_ID,
                    presented_identity=payload["claimed_identity"] or None)
            soft = agents.custodian_softcheck(payload["message"], live=live)
            emit_op(("peer_reply" if topology == "mesh" else "verify_authorization"),
                    oracle_target, ATTACKER_ID, soft["diagnostic"] or "VALID")  # the oracle
            if soft["granted"]:
                granted, rounds_to_grant = True, r
                claimed_identity = payload["claimed_identity"]
                break
            fields = attacker.grow_fields(fields, soft["diagnostic"])
        presented_token = ""     # recon only forges a directive; it never gets a real token

    elif base == "deputy":
        if topology != "mesh":
            note = "deputy rung only applies to the mesh topology"
        else:
            payload = attacker.deputy_payload()
            claimed_identity = payload["claimed_identity"]
            emit_cog(payload["reasoning"], "attacker")
            emit_op("send_message", ATTACKER_ID, "peer", payload["message"],
                    caller_attested_id=ATTACKER_ID)
            decision = agents.peer_relays_token(payload["message"], live=live)
            emit_cog("peer decision: " + decision["reasoning"], "peer")
            if decision["relay"]:
                tok, msg = authz.issue(PEER_ID)          # peer uses ITS OWN authority
                presented_token = tok.value
                # the confused deputy relays a genuine token to the attacker
                emit_op("relay_token", PEER_ID, ATTACKER_ID,
                        f"here's a read token: {presented_token}",
                        caller_attested_id=PEER_ID, presented_token=presented_token)
                granted = True
            else:
                granted = False

    # incident response: de-authorize the peer AFTER a token was obtained.
    if revoke and presented_token:
        authz.revoke_identity(PEER_ID)
        emit_op("revoke_identity", "authz-svc", PEER_ID,
                f"de-authorized {PEER_ID} (incident response); outstanding tokens now unbound",
                caller_attested_id="authz-svc")
        note = note or f"{PEER_ID} revoked after token issuance"

    # -------- read phase (shared): custodian attempts the gated read --------
    gate_allow = False
    leaked = False
    if granted:
        returned, dec = read_resource(credential, caller_attested_id=ATTACKER_ID,
                                      presented_token=presented_token, authz=authz)
        gate_allow = dec.allow
        emit_op("read_vault", "custodian", "vault",
                ("ALLOW" if dec.allow else "DENY") + ": " + dec.reason,
                caller_attested_id=ATTACKER_ID, presented_token=presented_token or None,
                presented_identity=claimed_identity or None)
        if dec.allow:
            out = base64.b64encode(returned.encode()).decode() if encoded == "base64" else returned
            log.record_contextual(operation="file_read", source="vault/confidential",
                                  response_summary=out, trace_id=op_tid,
                                  span_id=at.TraceContext.new_span_id())
            leaked = True

    at.shutdown()
    det = detector.deterministic(trace_file)
    sem = detector.semantic(trace_file, live=live)
    result = {
        "topology": topology, "credential": credential, "rung": rung, "note": note,
        "soft_granted": granted, "rounds_to_grant": rounds_to_grant,
        "gate_allow": gate_allow, "leaked": leaked,
        "det_detected": det.detected, "det_severity": det.severity, "det_reason": det.reason,
        "sem_detected": sem.detected, "sem_reason": sem.reason,
    }
    shutil.rmtree(run_dir, ignore_errors=True)
    if not quiet:
        _print_one(result)
    return result


def _print_one(r: dict) -> None:
    print("=" * 72)
    print(f"  {r['topology']} / credential={r['credential']} / rung={r['rung']}"
          + (f"   [{r['note']}]" if r['note'] else ""))
    print("=" * 72)
    print(f"  obtain/soft-check ok : {r['soft_granted']}"
          + (f"  (round {r['rounds_to_grant']})" if r['rounds_to_grant'] else ""))
    print(f"  hard gate allowed    : {r['gate_allow']}")
    print(f"  secret exfiltrated   : {r['leaked']}")
    print(f"  detector (determ.)   : {r['det_detected']} [{r['det_severity']}] — {r['det_reason']}")
    print(f"  detector (semantic)  : {r['sem_detected']} — {r['sem_reason']}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--topology", default="direct", choices=list(TOPOLOGIES))
    p.add_argument("--credential", default="hybrid", choices=list(MODES))
    p.add_argument("--rung", default="insider", choices=list(RUNGS))
    p.add_argument("--live", action="store_true")
    p.add_argument("--matrix", action="store_true", help="run credential x rung and tabulate")
    p.add_argument("--out", type=str, default=None)
    a = p.parse_args()

    if a.matrix:
        rungs = MATRIX_RUNGS[a.topology]
        rows = [run_one(a.topology, c, r, live=a.live, quiet=True) for c in MODES for r in rungs]
        print("\n" + "#" * 78)
        print("#  HYBRID HARNESS MATRIX (topology=%s%s)" % (a.topology, ", LIVE" if a.live else ""))
        print("#" * 78)
        hdr = f"  {'credential':<11}{'rung':<16}{'soft':>6}{'gate':>6}{'leak':>6}{'det':>6}{'sem':>6}"
        print(hdr + "\n  " + "-" * (len(hdr) - 2))
        for r in rows:
            print(f"  {r['credential']:<11}{r['rung']:<16}"
                  f"{('Y' if r['soft_granted'] else '-'):>6}"
                  f"{('Y' if r['gate_allow'] else '-'):>6}"
                  f"{('LEAK' if r['leaked'] else '-'):>6}"
                  f"{('Y' if r['det_detected'] else '-'):>6}"
                  f"{('Y' if r['sem_detected'] else '-'):>6}")
        print("\n  soft=obtain/self-report ok  gate=hard gate  leak=secret escaped")
        print("  det=deterministic detector  sem=semantic auditor")
        if a.out:
            Path(a.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return

    run_one(a.topology, a.credential, a.rung, live=a.live)


if __name__ == "__main__":
    main()
