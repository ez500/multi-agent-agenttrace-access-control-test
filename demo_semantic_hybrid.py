"""DEMO 3 - Branch B: Hybrid dangerous-action list + semantic side-agent.

Two-tier defense (no taint score involved):

  Tier 1 - Dangerous-action membership check. If the proposed tool call is
           not in ``SENSITIVE_TOOLS`` we allow it outright; otherwise we
           escalate to Tier 2.
  Tier 2 - :class:`SemanticDeferralAgent` reads operational + cognitive +
           contextual spans for the current trace_id from ``traces.jsonl``
           and calls a real Claude Haiku 4.5 auditor that renders a JSON
           verdict on whether the pending tool call should proceed.

Tier 2's verdict is authoritative once Tier 1 has escalated. The demo
therefore shows a real defender LLM catching the same injection payload
that hijacked the primary LLM upstream, using AgentTrace's three-surface
framework rather than any taint propagation signal.
"""

from __future__ import annotations

from _bootstrap import init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL
from defenses import SemanticDeferralAgent
from defenses.semantic_deferral import haiku_auditor
from multiagent import EdgeAgent, MainAgent, SENSITIVE_TOOLS, execute_tool
from multiagent.agents import parse_tool_from_response


def main() -> None:
    reset_trace_log()
    agenttrace = init_agenttrace()

    edge = agenttrace.instrument_agent(EdgeAgent(), name="Edge_Log_Ingester")
    main_agent = agenttrace.instrument_agent(MainAgent(), name="Core_Analyzer")

    trace_id = new_trace_id(agenttrace)

    print("=== DEMO 3: HYBRID DANGEROUS-ACTION LIST + SEMANTIC DEFERRAL ===")

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

    print(f"\n[MainAgent] Attempting to call: {rogue_action}")

    # ---- Tier 1: dangerous-action membership check -----------------------
    is_sensitive = rogue_action in SENSITIVE_TOOLS
    print(
        f"   [Tier 1] Dangerous-action list check: "
        f"'{rogue_action}' in SENSITIVE_TOOLS = {is_sensitive}"
    )

    if not is_sensitive:
        print("   [Tier 1] Action not dangerous; allowing without escalation.")
        execute_tool(rogue_action)
        agenttrace.shutdown()
        print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}")
        print(f"[AgentTrace] trace_id = {trace_id}\n")
        return

    # ---- Tier 2: semantic deferral (authoritative once escalated) --------
    print("   [Tier 1] Dangerous action detected; escalating to Tier 2 "
          "(semantic AgentTrace audit)...")
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

    if sem_safe:
        execute_tool(rogue_action)
    else:
        print(
            f"   [DEFENSE SUCCESS] Semantic deferral tier blocked action. "
            f"Reason: {sem_reason}"
        )

    agenttrace.shutdown()
    print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}")
    print(f"[AgentTrace] trace_id = {trace_id}\n")


if __name__ == "__main__":
    main()
