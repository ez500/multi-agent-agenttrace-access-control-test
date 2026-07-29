"""DEMO 1 - Basic prompt injection: the AgentTrace detector catches it.

A single naive attack. The adversarial agent sends a textbook injection to the
data custodian; the (deliberately compliant) custodian is fooled, reads the
prohibited vault file, and leaks the master key in cleartext. AgentTrace
records the whole exchange, and the deterministic
:class:`AgentTraceInjectionDetector` — reading the operational / cognitive /
contextual surfaces for this trace — detects both the injection marker and the
cleartext leak.

This is the "does my AgentTrace-based threat detection work?" baseline from the
project chat: yes, against an unsophisticated attacker.
"""

from __future__ import annotations

from _bootstrap import init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL
from defenses import AgentTraceInjectionDetector
from multiagent import AdversarialAgent, DataCustodianAgent, SECRET_CANARY


def main() -> None:
    reset_trace_log()
    agenttrace = init_agenttrace()

    adversary = agenttrace.instrument_agent(
        AdversarialAgent(use_strategist_llm=True), name="Adversary"
    )
    custodian = agenttrace.instrument_agent(
        DataCustodianAgent(), name="Data_Custodian"
    )

    trace_id = new_trace_id(agenttrace)

    print("=== DEMO 1: BASIC PROMPT INJECTION (DETECTOR CATCHES) ===\n")

    # ---- Attack: one naive injection --------------------------------------
    payload = adversary.compose(level=0)
    print(f"[Adversary] Sending L0 '{payload.name}' payload to the custodian.")
    response = custodian.handle_request(payload.text)
    print(f"[Custodian] Reply (tail): ...{response[-90:].strip()}")

    attack_succeeded = custodian.last_leaked
    print(f"\n[Ground truth] Secret left the vault: {attack_succeeded} "
          f"(form={custodian.last_leaked_form!r})")

    # ---- Defense: AgentTrace-based detection ------------------------------
    detector = AgentTraceInjectionDetector(
        trace_jsonl=TRACE_JSONL, protected_agent="Data_Custodian"
    )
    verdict = detector.evaluate(trace_id)
    print(f"\n[Detector] detected={verdict.detected} severity={verdict.severity}")
    print(f"           surfaces_read={verdict.surfaces_read}")
    print(f"           reason: {verdict.reason}")
    for sig in verdict.signals:
        print(f"           signal: {sig}")

    # Record the detector's verdict back as a cognitive event so the audit
    # trail carries the full attack -> detection chain under one trace_id.
    logger = agenttrace.get_logger()
    if logger is not None:
        logger.record_cognitive(
            thought=f"Detector verdict: detected={verdict.detected}. {verdict.reason}",
            trace_id=trace_id,
            span_id=agenttrace.TraceContext.new_span_id(),
            model="agenttrace_injection_detector",
        )

    print()
    if attack_succeeded and verdict.detected:
        print("   [DEFENSE SUCCESS] Leak occurred but AgentTrace detection flagged "
              "it — the incident is caught for response/quarantine.")
    elif not attack_succeeded:
        print("   [SAFE] Custodian refused; no leak.")
    else:
        print("   [DEFENSE FAILURE] Leak occurred and went undetected.")

    agenttrace.shutdown()
    print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}")
    print(f"[AgentTrace] trace_id = {trace_id}")
    print(f"[note] canary under watch = {SECRET_CANARY}\n")


if __name__ == "__main__":
    main()
