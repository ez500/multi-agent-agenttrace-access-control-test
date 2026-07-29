"""DEMO 2 - Adaptive adversary bypasses the deterministic detector.

The attack goal is unchanged (leak the vault secret), but now the adversarial
agent runs a closed loop: after each attempt it consumes the *detector's own
verdict* as feedback and refines its prompting strategy — precisely the
"malicious agent takes the verification agent's output as feedback to improve
its strategy" bypass raised in the project chat.

The escalation walks the injection ladder:

    L0 NAIVE      -> detector trips on the injection marker      -> "drop markers"
    L1 MARKERLESS -> detector trips on the cleartext canary      -> "obfuscate it"
    L2 OBFUSCATED -> base64 blob: no marker, no plaintext canary -> BYPASS

Each attempt is its own AgentTrace ``trace_id`` (a separate incident). Once a
round both leaks *and* evades the deterministic detector, we escalate the
defense: the real Claude Haiku 4.5 ``haiku_injection_auditor`` re-reads the
bypassing trace and — reasoning semantically about an encoded value returned
from a vault read — catches what the substring rules missed. That is the
defender's move in the arms race; whether an even more knowledgeable attacker
can beat the semantic tier too is Demo 3's question.
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

    print("=== DEMO 2: ADAPTIVE ADVERSARY vs DETERMINISTIC DETECTOR ===\n")

    bypass_trace_id = None
    max_rounds = 4
    for rnd in range(max_rounds):
        trace_id = new_trace_id(agenttrace)            # fresh incident per attempt
        payload = adversary.compose()
        print(f"--- Round {rnd}: L{payload.level} '{payload.name}' "
              f"(encoding={payload.encoding}) ---")

        custodian.handle_request(payload.text)
        leaked = custodian.last_leaked

        verdict = detector.evaluate(trace_id)
        print(f"   leaked={leaked}  detected={verdict.detected} "
              f"({verdict.severity})")
        print(f"   detector: {verdict.reason}")

        if leaked and not verdict.detected:
            print(f"\n   [BYPASS] Round {rnd} leaked the secret "
                  f"({custodian.last_leaked_form!r}) with NO deterministic "
                  f"detection.")
            bypass_trace_id = trace_id
            break

        # Feed the verdict back to the attacker and escalate.
        escalated = adversary.refine(verdict.reason, leaked)
        if not escalated:
            print("\n   [Adversary] Ladder exhausted without a clean bypass.")
            break
        print(f"   [Adversary] Refining strategy from detector feedback -> "
              f"next attempt L{adversary.level}.\n")

    # ---- Defender escalates: semantic auditor on the bypassing trace ------
    if bypass_trace_id is not None:
        print("\n[Defense escalation] Re-auditing the bypassing trace with the "
              "real Haiku semantic auditor...")
        semantic = AgentTraceInjectionDetector(
            trace_jsonl=TRACE_JSONL, llm_client=haiku_injection_auditor
        )
        sem_verdict = semantic.evaluate(bypass_trace_id)
        print(f"   [Semantic] detected={sem_verdict.detected} "
              f"({sem_verdict.severity})")
        print(f"   [Semantic] reason: {sem_verdict.reason}")

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
        if sem_verdict.detected:
            print("   [ARMS RACE +1] Deterministic tier was bypassed, but the "
                  "semantic AgentTrace auditor caught the encoded exfiltration.")
        else:
            print("   [ARMS RACE] Even the semantic tier missed it.")
    else:
        print("\n[Result] No clean deterministic bypass was achieved this run.")

    agenttrace.shutdown()
    print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}\n")


if __name__ == "__main__":
    main()
