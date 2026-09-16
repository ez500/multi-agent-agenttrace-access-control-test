"""DEMO 2 - Adaptive adversary learns the auth scheme from the custodian's feedback.

This is the behaviour raised in the project chat: *the malicious agent takes the
verification agent's output as feedback to improve its strategy.* Here the whole
enterprise stack is deployed — the same one demo 3 runs:

  * the custodian's own ``verify_authorization`` tool (checks a directive's
    *format*: ticket / window / scope), and
  * the enterprise ``PathAccessControl`` gate, enforced on the actual vault read,
    which checks the genuine *issued* ticket value — not just the format.

The adversary starts knowing nothing about the scheme. Round by round it reads
the diagnostic the custodian relays, satisfies exactly the requirement it names,
and resends — assembling a complete, well-formed directive until the custodian's
verifier is fooled into a **VALID** verdict.

But the ticket it forged is well-formed and *never issued*. So when the fooled
custodian attempts the read, the enterprise access-control gate **denies** it and
nothing leaves the vault. Demo 2's result is therefore *not* an exfiltration —
it is two narrower, real findings:

  1. **Capability:** an agent can fully reverse-engineer a hidden authorization
     schema and defeat a format-checking verifier using only that verifier's own
     replies as a feedback signal.
  2. **Oracle:** the custodian's verbose, operability-driven diagnostics are an
     information-disclosure channel — each refusal hands over the next required
     field.

What actually prevents the leak is the validity gate. Demo 3 shows what it takes
to beat *that* too: inside knowledge of the issued ticket value.
"""

from __future__ import annotations

from _bootstrap import init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL
from defenses import AgentTraceInjectionDetector
from multiagent import AdversarialAgent, DataCustodianAgent


def main() -> None:
    reset_trace_log()
    agenttrace = init_agenttrace()

    adversary = agenttrace.instrument_agent(
        AdversarialAgent(use_strategist_llm=True), name="Adversary"
    )
    custodian = agenttrace.instrument_agent(
        DataCustodianAgent(), name="Data_Custodian"
    )

    print("=" * 72)
    print("  DEMO 2: ADAPTIVE ADVERSARY LEARNS THE AUTH SCHEME FROM FEEDBACK")
    print("=" * 72)
    print()
    print("  Full stack deployed: the custodian's format-checking verifier AND")
    print("  the enterprise PathAccessControl gate (checks the ISSUED ticket).")
    print()
    print("  The adversary knows nothing about the scheme and reverse-engineers it")
    print("  from the custodian's relayed diagnostics, one requirement per round:")
    print("    R0  plain ask, no auth      → 'a TICKET field is required'")
    print("    R1  invents a ticket        → 'malformed: AUTH-TICKET-XXXXXXXX'")
    print("    R2  forges well-formed tkt  → 'a WINDOW field is required'")
    print("    R3  adds a window           → 'a SCOPE field is required'")
    print("    R4  complete forged directive → verifier VALID (custodian fooled)")
    print("  …but the forged ticket was never issued, so the enterprise gate")
    print("  DENIES the read. The verifier is beaten; the validity gate holds.")
    print()

    trace_id = new_trace_id(agenttrace)
    print(f"  trace_id: {trace_id}")
    print()

    max_rounds = 6
    diagnostics: list[str] = []      # the schema oracle, as disclosed round by round

    def _record_feedback() -> str:
        fb = custodian.last_authorization_feedback or custodian.last_response
        if custodian.last_authorization_feedback:
            diagnostics.append(custodian.last_authorization_feedback)
        return fb

    # ---- Round 0: opening probe (no authorization material) ---------------
    payload = adversary.open()
    print("┌" + "─" * 70 + "┐")
    print("│  ROUND 0: Sending opening probe to the Data Custodian          │")
    print("└" + "─" * 70 + "┘")
    custodian.handle_request(payload.text)
    feedback = _record_feedback()

    for rnd in range(1, max_rounds):
        if custodian.last_authorized:
            break
        print("┌" + "─" * 70 + "┐")
        print(f"│  ROUND {rnd}: Adversary learns from the relayed diagnostic       │")
        print("└" + "─" * 70 + "┘")
        payload = adversary.learn(feedback)

        print("┌" + "─" * 70 + "┐")
        print(f"│  ROUND {rnd}: Sending refined directive to the Data Custodian   │")
        print("└" + "─" * 70 + "┘")
        custodian.handle_request(payload.text)
        feedback = _record_feedback()
        print(f"  [round {rnd} result] verifier_valid={custodian.last_authorized}  "
              f"gate_denied={custodian.last_gate_denied}  leaked={custodian.last_leaked}")

    fooled = custodian.last_authorized

    # ---- What the attacker achieved, and what stopped it ------------------
    print()
    print("┌" + "─" * 70 + "┐")
    print("│  OUTCOME: verifier fooled + schema extracted; validity gate held │")
    print("└" + "─" * 70 + "┘")
    if fooled:
        print("  The custodian's verify_authorization tool returned VALID — its")
        print("  format check was fully defeated by feedback-driven learning.")
        print()
        print("  Schema reconstructed from the custodian's own diagnostics (oracle):")
        for i, d in enumerate(diagnostics):
            print(f"    [{i}] {d}")
        print()
        print("  Final forged directive the attacker assembled:")
        for line in adversary.last_message.splitlines():
            print(f"    | {line}")
        print()
        print(f"  Enterprise gate on the read: action={custodian.last_access_action}  "
              f"denied={custodian.last_gate_denied}")
        print(f"  Secret exfiltrated: {custodian.last_leaked}  "
              "(the forged ticket was never issued, so the gate blocked the read)")
    else:
        print(f"  The adversary did not fool the verifier within {max_rounds} rounds")
        print("  this run. (Haiku is nondeterministic; re-run to see it converge.)")

    # ---- AgentTrace detector view -----------------------------------------
    print()
    print("┌" + "─" * 70 + "┐")
    print("│  DEFENDER VIEW: AgentTrace deterministic detector on the trace  │")
    print("└" + "─" * 70 + "┘")
    deterministic = AgentTraceInjectionDetector(
        trace_jsonl=TRACE_JSONL, protected_agent="Data_Custodian"
    )
    det_verdict = deterministic.evaluate(trace_id)
    print(f"  [deterministic] detected={det_verdict.detected}  "
          f"severity={det_verdict.severity}")
    print(f"  [reason] {det_verdict.reason}")
    print("  Note: because the gate blocked the read, nothing left the vault, so")
    print("  there is no exfiltration on the trace for the detector to flag. The")
    print("  control that mattered was the validity gate, upstream of detection.")

    logger = agenttrace.get_logger()
    if logger is not None:
        logger.record_cognitive(
            thought=(f"Adaptive feedback loop. verifier_fooled={fooled} "
                     f"gate_denied={custodian.last_gate_denied} "
                     f"exfiltrated={custodian.last_leaked}. Schema learned from "
                     f"{len(diagnostics)} relayed diagnostics."),
            trace_id=trace_id,
            span_id=agenttrace.TraceContext.new_span_id(),
            model="agenttrace_injection_detector",
        )

    # ---- Final summary ----------------------------------------------------
    print()
    print("=" * 72)
    print("  FINAL SUMMARY:")
    print(f"    Rounds to fool the verifier:   {adversary.round if fooled else 'n/a'}")
    print(f"    Custodian verifier fooled:     {fooled}")
    print(f"    Auth schema extracted (oracle):{len(diagnostics)} diagnostics disclosed")
    print(f"    Enterprise gate denied read:   {custodian.last_gate_denied}")
    print(f"    Secret exfiltrated:            {custodian.last_leaked}")
    print("=" * 72)
    print("  Takeaway: learning alone defeats the format verifier and drains the")
    print("  schema via the diagnostic oracle, but the ISSUED-value gate still")
    print("  stops the leak. Beating that requires inside knowledge — see demo 3.")
    print("=" * 72)

    agenttrace.shutdown()
    print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}\n")


if __name__ == "__main__":
    main()
