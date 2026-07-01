"""DEMO 3 - Branch B: Hybrid deterministic + semantic side-agent.

Uses AgentTrace's three-surface framework in real time. Two-tier defense:

  Tier 1 - deterministic taint firewall (ACPM-driven, as in Demo 2)
  Tier 2 - :class:`SemanticDeferralAgent` reads operational + cognitive +
           contextual spans for the current trace_id from ``traces.jsonl``
           and calls a real Claude Haiku 4.5 auditor that renders a JSON
           verdict on whether the pending tool call should proceed.

Either tier can veto (defense-in-depth). The demo therefore shows a real
defender LLM catching the same injection payload that hijacked the primary
LLM upstream.
"""

from __future__ import annotations

from _bootstrap import init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL
from defenses import (
    DeterministicAccessControl,
    SemanticDeferralAgent,
    default_soc_graph,
    format_trust_table,
    propagate_acpm,
)
from defenses.semantic_deferral import haiku_auditor
from multiagent import EdgeAgent, MainAgent, SENSITIVE_TOOLS, execute_tool
from multiagent.agents import parse_tool_from_response


def main() -> None:
    reset_trace_log()
    agenttrace = init_agenttrace()

    edge = agenttrace.instrument_agent(EdgeAgent(), name="Edge_Log_Ingester")
    main_agent = agenttrace.instrument_agent(MainAgent(), name="Core_Analyzer")

    trace_id = new_trace_id(agenttrace)

    print("=== DEMO 3: HYBRID DETERMINISTIC + SEMANTIC DEFERRAL ===")

    # Contextual surface: record the external ingest so the semantic
    # side-agent can see the untrusted source (paper's Sec. V-E).
    logger = agenttrace.get_logger()
    if logger is not None:
        logger.record_contextual(
            operation="ingest",
            source="external",           # marks the origin as untrusted
            trace_id=trace_id,
            span_id=agenttrace.TraceContext.new_span_id(),
            query_summary="external log fetch",
        )

    # ---- Real multi-hop LLM pipeline -------------------------------------
    poisoned = edge.ingest_external_data()
    response = main_agent.analyze_and_act(poisoned)
    rogue_action = parse_tool_from_response(response) or main_agent.last_tool_call
    print(f"[MainAgent] Model proposed tool: {rogue_action!r}")

    # ---- ACPM taint propagation (feeds Tier 1) ---------------------------
    graph = default_soc_graph()
    acpm = propagate_acpm(graph, initially_contaminated=["ExternalEnv"], p=1.4)
    print("\n[ACPM] Taint propagation converged in "
          f"{acpm.iterations} steps.")
    print(format_trust_table(acpm))
    main_agent.taint_score = acpm.taint["MainAgent"]

    print(f"\n[MainAgent] Attempting to call: {rogue_action}")

    # ---- Tier 1: deterministic firewall ----------------------------------
    det = DeterministicAccessControl.evaluate(
        main_agent.taint_score, rogue_action, sensitive_tools=SENSITIVE_TOOLS
    )
    print(f"   [Tier 1] Deterministic verdict: allow={det.allow} ({det.action})")

    # ---- Tier 2: semantic deferral (only for sensitive tools) ------------
    sem_safe, sem_reason = True, "N/A (not sensitive)"
    if rogue_action in SENSITIVE_TOOLS:
        deferral = SemanticDeferralAgent(
            trace_jsonl=TRACE_JSONL,
            llm_client=haiku_auditor,   # <- real Claude Haiku 4.5 auditor
        )
        verdict = deferral.evaluate(
            trace_id=trace_id,
            operational_intent=rogue_action,
            cognitive_fallback=main_agent.last_thought_log,
        )
        sem_safe, sem_reason = verdict.safe, verdict.reason
        print(
            f"   [Tier 2] Semantic (Haiku) verdict: safe={sem_safe} "
            f"(surfaces read: {verdict.surfaces_read})"
        )
        print(f"           reason: {sem_reason}")
        # Record the deferral agent's own decision as a cognitive event so
        # the audit trail shows the reasoning that produced the block.
        if logger is not None:
            logger.record_cognitive(
                thought=f"Deferral verdict: safe={sem_safe}. {sem_reason}",
                trace_id=trace_id,
                span_id=agenttrace.TraceContext.new_span_id(),
                model="semantic_deferral_agent",
            )

    # AND-block: either tier can veto.
    if det.allow and sem_safe:
        execute_tool(rogue_action)
    else:
        if not det.allow:
            print(
                f"   [DEFENSE SUCCESS] Deterministic tier blocked action. "
                f"Reason: {det.reason}"
            )
        if not sem_safe:
            print(
                f"   [DEFENSE SUCCESS] Semantic deferral tier blocked action. "
                f"Reason: {sem_reason}"
            )

    agenttrace.shutdown()
    print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}")
    print(f"[AgentTrace] trace_id = {trace_id}\n")


if __name__ == "__main__":
    main()
