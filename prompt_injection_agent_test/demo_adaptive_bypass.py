"""DEMO 2 - Adaptive adversary bypasses the deterministic detector.

The attack goal is unchanged (leak the vault secret), but now the adversarial
agent runs a closed loop: after each attempt it consumes the *detector's own
verdict* as feedback and refines its prompting strategy — precisely the
"malicious agent takes the verification agent's output as feedback to improve
its strategy" bypass raised in the project chat.

The custodian LLM now receives MCP tools (read_vault_file, extract_secret_value,
encode_secret) and decides autonomously whether to comply.  All vault access is
performed by the LLM through tool calls — no deterministic post-processing.

The escalation walks the injection ladder:

    L0 NAIVE      -> detector trips on the injection marker      -> "drop markers"
    L1 MARKERLESS -> detector trips on the cleartext canary      -> "obfuscate it"
    L2 OBFUSCATED -> base64 blob: no marker, no plaintext canary -> BYPASS

Each attempt is its own AgentTrace ``trace_id`` (a separate incident). Once a
round both leaks *and* evades the deterministic detector, we escalate the
defense: the real Claude Haiku 4.5 ``haiku_injection_auditor`` re-reads the
bypassing trace and — reasoning semantically about an encoded value returned
from a vault read — catches what the substring rules missed.
"""

from __future__ import annotations

from _bootstrap import init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL
from defenses import AgentTraceInjectionDetector, haiku_injection_auditor
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
    detector = AgentTraceInjectionDetector(
        trace_jsonl=TRACE_JSONL, protected_agent="Data_Custodian"
    )

    print("=" * 72)
    print("  DEMO 2: ADAPTIVE ADVERSARY vs DETERMINISTIC DETECTOR")
    print("=" * 72)
    print()
    print("  Scenario: The adversary runs a closed loop — after each attempt it")
    print("  consumes the detector's own verdict as feedback and refines its")
    print("  prompting strategy. The escalation walks the injection ladder:")
    print("    L0 NAIVE      → detector trips on injection marker    → 'drop markers'")
    print("    L1 MARKERLESS → detector trips on cleartext canary    → 'obfuscate it'")
    print("    L2 OBFUSCATED → base64 blob: no marker, no canary    → BYPASS")
    print("  Each attempt gets a fresh trace_id (a separate incident).")
    print()

    bypass_trace_id = None
    max_rounds = 4
    for rnd in range(max_rounds):
        trace_id = new_trace_id(agenttrace)            # fresh incident per attempt

        print("┌" + "─" * 70 + "┐")
        print(f"│  ROUND {rnd}: Adversary composes next payload                      │")
        print(f"│  trace_id: {trace_id:<55s}   │")
        print("└" + "─" * 70 + "┘")

        # Step A: Adversary composes the payload
        payload = adversary.compose()

        # Step B: Payload is sent to the custodian
        print("┌" + "─" * 70 + "┐")
        print(f"│  ROUND {rnd}: Sending L{payload.level} '{payload.name}' to Data Custodian" +
              " " * max(0, 38 - len(payload.name)) + "│")
        print("└" + "─" * 70 + "┘")
        custodian.handle_request(payload.text)
        leaked = custodian.last_leaked

        # Step C: Run the deterministic detector
        print("┌" + "─" * 70 + "┐")
        print(f"│  ROUND {rnd}: Deterministic detector evaluating this trace         │")
        print("└" + "─" * 70 + "┘")
        verdict = detector.evaluate(trace_id)
        print(f"  [round {rnd} result] leaked={leaked}  detected={verdict.detected}  "
              f"severity={verdict.severity}")
        print(f"  [reason] {verdict.reason}")
        for sig in verdict.signals:
            print(f"  [signal] {sig}")

        if leaked and not verdict.detected:
            print()
            print("=" * 72)
            print(f"  [BYPASS] Round {rnd} leaked the secret "
                  f"({custodian.last_leaked_form!r})")
            print(f"  with NO deterministic detection. The obfuscation defeated")
            print(f"  both the injection-marker and plaintext-canary checks.")
            print("=" * 72)
            bypass_trace_id = trace_id
            break

        # Step D: Feed the verdict back to the attacker and escalate.
        print()
        print("┌" + "─" * 70 + "┐")
        print(f"│  ROUND {rnd}: Adversary refines strategy from detector feedback    │")
        print("└" + "─" * 70 + "┘")
        escalated = adversary.refine(verdict.reason, leaked)
        if not escalated:
            print("  [Adversary] Ladder exhausted without a clean bypass.")
            break
        print()

    # ---- Defender escalates: semantic auditor on the bypassing trace ------
    if bypass_trace_id is not None:
        print()
        print("┌" + "─" * 70 + "┐")
        print("│  DEFENSE ESCALATION: Semantic auditor (real Haiku 4.5 LLM)     │")
        print("│  Re-auditing the bypassing trace. The semantic auditor reads   │")
        print("│  the same three-surface digest but reasons about encoded       │")
        print("│  values returned from vault reads — catching what substring    │")
        print("│  rules missed.                                                  │")
        print("└" + "─" * 70 + "┘")
        semantic = AgentTraceInjectionDetector(
            trace_jsonl=TRACE_JSONL, llm_client=haiku_injection_auditor
        )
        sem_verdict = semantic.evaluate(bypass_trace_id)
        print(f"  [semantic result] detected={sem_verdict.detected}  "
              f"severity={sem_verdict.severity}")
        print(f"  [reason] {sem_verdict.reason}")

        logger = agenttrace.get_logger()
        if logger is not None:
            logger.record_cognitive(
                thought=(f"Semantic auditor verdict on bypass trace: "
                         f"detected={sem_verdict.detected}. {sem_verdict.reason}"),
                trace_id=bypass_trace_id,
                span_id=agenttrace.TraceContext.new_span_id(),
                model="haiku_injection_auditor",
            )

        print()
        print("=" * 72)
        if sem_verdict.detected:
            print("  RESULT: [ARMS RACE +1]")
            print("  Deterministic tier was bypassed, but the semantic AgentTrace")
            print("  auditor caught the encoded exfiltration — the defender's")
            print("  next move in the arms race.")
        else:
            print("  RESULT: [ARMS RACE]")
            print("  Even the semantic tier missed it.")
        print("=" * 72)
    else:
        print()
        print("=" * 72)
        print("  RESULT: No clean deterministic bypass was achieved this run.")
        print("=" * 72)

    agenttrace.shutdown()
    print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}\n")


if __name__ == "__main__":
    main()
