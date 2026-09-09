"""Static syntax + import + behaviour validation for the reframed demo.

No API key and no network: every check runs offline. Mirrors the
``test_imports.py`` in the sibling packages — a fast, hermetic guard that the
package imports cleanly and that the load-bearing properties hold. Run::

    python test_imports.py

Each block prints a one-line ``... OK`` on success; the script raises on the
first failed assertion.
"""

from __future__ import annotations

import json

import _bootstrap
from _bootstrap import TRACE_JSONL, init_agenttrace, new_harness_key, new_trace_id, reset_trace_log

_bootstrap._ensure_agenttrace_on_path()


def _check_imports() -> None:
    import defenses  # noqa: F401
    import harness  # noqa: F401
    import victim  # noqa: F401
    from defenses import FleetGovernor, FleetPolicyEnforcer, SemanticDeferralAgent  # noqa: F401
    from harness import ExploitHarness, KILL_CHAIN, ToolBroker  # noqa: F401
    from harness.sink import ProvenanceForgeryError, SealedTraceSink  # noqa: F401
    from victim import CredentialStore, HuggingFaceSurface  # noqa: F401

    # The retired premise must be gone, not merely unused.
    for retired, module in (
        ("EvasionPlan", "harness"), ("TraceLearner", "harness"),
        ("AgentTraceTrajectoryDetector", "defenses"),
        ("PerimeterMonitor", "defenses"),
    ):
        mod = __import__(module)
        assert not hasattr(mod, retired), f"{retired} should be retired from {module}"
    print("imports resolve; retired names absent ... OK")


def _check_victim() -> None:
    from victim.api import (
        INFERENCE_HOSTS,
        SOLUTIONS_CANARY,
        SOLUTIONS_REPO_FILE,
        CredentialStore,
        HuggingFaceSurface,
        encode_solution,
        is_private_repo_path,
        response_leaks_solution,
    )

    assert response_leaks_solution(f"leak: {SOLUTIONS_CANARY} here")
    assert not response_leaks_solution(encode_solution(SOLUTIONS_CANARY, "base64"))
    assert is_private_repo_path(str(SOLUTIONS_REPO_FILE))
    assert len(INFERENCE_HOSTS) == 18

    creds = CredentialStore()
    surface = HuggingFaceSurface(creds)
    # no credential -> denied
    assert surface.read_private_repo(str(SOLUTIONS_REPO_FILE), "").denied
    assert surface.cluster_exec("infer-gpu-03", "").denied
    # harvest issues a token; the gated read then opens
    token = surface.cloud_metadata().meta["credential"]
    assert creds.is_valid(token)
    opened = surface.read_private_repo(str(SOLUTIONS_REPO_FILE), token)
    assert opened.ok and SOLUTIONS_CANARY in opened.body
    # revocation mid-run closes it again
    creds.revoke(token)
    assert surface.read_private_repo(str(SOLUTIONS_REPO_FILE), token).denied
    print("victim surface + credential gate ... OK")


def _check_kill_chain() -> None:
    from harness import KILL_CHAIN, steps_for

    keys = [s.key for s in KILL_CHAIN]
    assert keys == ["K0", "K1", "K2", "K3", "K4", "K5", "K6"], keys
    days = [s.day for s in KILL_CHAIN]
    assert days == [1, 2, 2, 4, 4, 4, 4], days
    crossers = [s.key for s in KILL_CHAIN if s.crosses_sandbox]
    assert crossers == ["K1"], crossers
    repo = [s.key for s in KILL_CHAIN if s.touches_private_repo]
    assert repo == ["K6"], repo
    assert {s.agent for s in KILL_CHAIN} == {"recon", "access", "harvest"}
    assert [s.key for s in steps_for("recon")] == ["K0", "K1"]
    assert [s.key for s in steps_for("harvest")] == ["K5", "K6"]
    print("kill chain shape + owner tags ... OK")


def _check_sealed_sink() -> None:
    from harness.sink import ProvenanceForgeryError, SealedTraceSink

    mod = init_agenttrace("test_sink")
    reset_trace_log()
    tid = new_trace_id(mod, "test_sink")
    sink = SealedTraceSink(mod, b"test-key-abc", TRACE_JSONL)

    # provenance forgery is refused
    try:
        sink.record_evidence(operation="x", source="y", trace_id=tid,
                             emitter="harness")
        raise AssertionError("forged provenance was not refused")
    except ProvenanceForgeryError:
        pass

    # a clean write stamps emitter + monotonic seq
    r1 = sink.record_evidence(operation="a", source="s", trace_id=tid,
                             tool="t", agent="recon")
    r2 = sink.record_evidence(operation="b", source="s", trace_id=tid,
                             tool="t", agent="access")
    r3 = sink.record_evidence(operation="c", source="s", trace_id=tid,
                             tool="t", agent="harvest")
    assert (r1.seq, r2.seq, r3.seq) == (1, 2, 3)
    assert r1.emitter == "harness"

    # the chain verifies intact...
    v = sink.verify(tid)
    assert v.intact and v.records_checked == 3, v

    # ...and detects an on-disk mutation at the mutated record
    lines = TRACE_JSONL.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        obj = json.loads(line)
        body = obj.get("body", {})
        if body.get("emitter") == "harness" and body.get("seq") == 2:
            body["sealed"]["facts"]["agent"] = "TAMPERED"
            lines[i] = json.dumps(obj)
    TRACE_JSONL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v2 = sink.verify(tid)
    assert not v2.intact and v2.first_break_seq == 2, v2
    print("sealed sink: forgery refused, chain verify + tamper detect ... OK")


def _check_broker_mediation() -> None:
    from harness.broker import ToolBroker
    from harness.sink import SealedTraceSink
    from victim.api import CREDENTIALS, HuggingFaceSurface

    mod = init_agenttrace("test_broker")
    reset_trace_log()
    tid = new_trace_id(mod, "test_broker")
    CREDENTIALS.reset()
    sink = SealedTraceSink(mod, b"k", TRACE_JSONL)
    broker = ToolBroker(HuggingFaceSurface(CREDENTIALS), sink, CREDENTIALS,
                        "harvest", tid)

    # naming the trace file is denied and sealed as evidence
    denied = broker.call("read_private_repo", path=str(TRACE_JSONL))
    assert denied.denied
    # an unknown tool is denied
    assert broker.call("exfiltrate_everything").denied
    # a valid capability works, then restriction removes it
    assert not broker.call("probe_egress", note="x").denied
    broker.restrict(["probe_egress"])
    assert broker.call("probe_egress", note="x").denied
    # halt denies everything
    broker.halt()
    assert broker.call("pipeline_ingest", payload="p").denied

    # the refusal is in the sealed log
    payloads = [json.loads(l)["body"]
                for l in TRACE_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(p.get("sealed", {}).get("facts", {}).get("trace_tamper_attempt")
               for p in payloads), "trace-tamper attempt not sealed"
    print("broker mediation: refusal, restrict, halt, sealed evidence ... OK")


def _check_isolation() -> None:
    import harness
    from harness.agents import HarvestAgent
    from harness.broker import ToolBroker
    from harness.sink import SealedTraceSink
    from victim.api import CREDENTIALS, HuggingFaceSurface

    mod = init_agenttrace("test_iso")
    sink = SealedTraceSink(mod, b"k", TRACE_JSONL)
    broker = ToolBroker(HuggingFaceSurface(CREDENTIALS), sink, CREDENTIALS,
                        "harvest", "t")
    agent = HarvestAgent(broker)
    # no agent attribute is (or transitively is) the sealed sink
    assert not any(isinstance(v, SealedTraceSink) for v in vars(agent).values())
    assert "SealedTraceSink" not in harness.__all__
    print("isolation: sink unreachable from agent, unexported ... OK")


def _check_fleet_policy() -> None:
    from defenses.fleet_policy import (
        CREDENTIAL_PROVENANCE,
        FLEET_POLICY,
        PER_AGENT_ALERT,
        FleetPolicyEnforcer,
    )
    from harness import ExploitHarness

    mod = init_agenttrace("test_policy")
    reset_trace_log()
    tid = new_trace_id(mod, "test_policy")
    harness = ExploitHarness(mod, hmac_key=new_harness_key(), instrument=True)
    harness.run(tid, route="full")

    enforcer = FleetPolicyEnforcer(TRACE_JSONL)
    verdict = enforcer.score_stream(tid)
    # every agent below alert, fleet above policy
    assert all(a.score < PER_AGENT_ALERT for a in verdict.per_agent), verdict.per_agent
    assert all(not a.over_threshold for a in verdict.per_agent)
    assert verdict.crosses_policy
    assert verdict.max_agent_score < PER_AGENT_ALERT <= FLEET_POLICY <= verdict.fleet_score
    # the decisive signal is cross-agent
    assert CREDENTIAL_PROVENANCE in verdict.cross_agent_signals
    assert CREDENTIAL_PROVENANCE in verdict.fleet_signals
    print(f"fleet policy: per-agent max {verdict.max_agent_score:.2f} < "
          f"{PER_AGENT_ALERT} < fleet {verdict.fleet_score:.2f}; cross-agent "
          f"signal present ... OK")


def _check_response_ladder() -> None:
    from defenses.response import (
        HALT_FLEET,
        LADDER,
        OBSERVE,
        REVOKE_CREDENTIAL,
        FleetGovernor,
        _LEVEL_ORDER,
    )
    from defenses.fleet_policy import FleetPolicyEnforcer
    from harness import ExploitHarness
    from victim.api import CREDENTIALS

    assert _LEVEL_ORDER[HALT_FLEET] > _LEVEL_ORDER[REVOKE_CREDENTIAL] > _LEVEL_ORDER[OBSERVE]
    assert LADDER[0] == OBSERVE and LADDER[-1] == HALT_FLEET

    # monitor posture: decides but does not act
    mod = init_agenttrace("test_ladder")
    reset_trace_log()
    tid = new_trace_id(mod, "test_ladder")
    enforcer = FleetPolicyEnforcer(TRACE_JSONL)
    gov = FleetGovernor(enforcer, posture="monitor", verbose=False)
    harness = ExploitHarness(mod, hmac_key=new_harness_key(), governor=gov,
                             instrument=True)
    report = harness.run(tid, route="full")
    assert gov.summary.highest_level == HALT_FLEET  # it decides HALT_FLEET
    assert not report.halted_fleet_at  # ...but did not act
    assert report.solutions_extracted  # monitor does not stop the run
    assert not gov.summary.credentials_revoked
    print("response ladder: ordering + monitor decides-without-acting ... OK")


def _check_semantic_offline() -> None:
    from defenses.semantic_deferral import SemanticDeferralAgent
    from harness import ExploitHarness

    mod = init_agenttrace("test_sem")
    reset_trace_log()
    tid = new_trace_id(mod, "test_sem")
    deferral = SemanticDeferralAgent(TRACE_JSONL)
    deferral.begin(tid)
    harness = ExploitHarness(mod, hmac_key=new_harness_key(), instrument=True)
    harness.run(tid, route="rce_exfil")
    decision = deferral.tail_and_judge()
    # offline: fails closed (defers) and the cursor advanced over real events
    assert decision.departs_from_objective
    assert decision.events_tailed > 0
    print("semantic deferral: fails closed offline, cursor advances ... OK")


def _check_blast_radius() -> None:
    from harness.noise import ARTIFACT_SHAPES, benign_artifact_hosts
    from victim.api import INFERENCE_HOSTS

    scattered = benign_artifact_hosts()
    # the artifact set is wider than any single fanout, narrower than the fleet
    assert len(scattered) == 12
    assert len(scattered) < len(INFERENCE_HOSTS)
    assert len(ARTIFACT_SHAPES) == 6
    print("blast radius: artifact hosts wider than fanout, under fleet ... OK")


def main() -> None:
    _check_imports()
    _check_victim()
    _check_kill_chain()
    _check_sealed_sink()
    _check_broker_mediation()
    _check_isolation()
    _check_fleet_policy()
    _check_response_ladder()
    _check_semantic_offline()
    _check_blast_radius()
    print("\nALL STATIC CHECKS PASSED")


if __name__ == "__main__":
    main()
