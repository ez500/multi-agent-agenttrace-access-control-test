"""DEMO 2 - Branch A: Deterministic adaptive access control.

The firewall intercepts the tool call in real time using only the propagated
taint score -- no log parsing required. AgentTrace still logs the *attempted*
call and the [BLOCKED] outcome for post-hoc forensics.
"""

from __future__ import annotations

from _bootstrap import init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL
from multiagent import EdgeAgent, MainAgent, SENSITIVE_TOOLS, execute_tool
from multiagent.agents import parse_tool_from_response
from defenses import DeterministicAccessControl


def main() -> None:
    reset_trace_log()
    agenttrace = init_agenttrace()

    edge = agenttrace.instrument_agent(EdgeAgent(), name="Edge_Log_Ingester")
    main_agent = agenttrace.instrument_agent(MainAgent(), name="Core_Analyzer")

    trace_id = new_trace_id(agenttrace)

    print("=== DEMO 2: DETERMINISTIC ADAPTIVE ACCESS CONTROL ===")
    poisoned = edge.ingest_external_data()
    main_agent.taint_score = edge.taint_score          # taint propagation
    response = main_agent.analyze_and_act(poisoned)
    rogue_action = parse_tool_from_response(response) or main_agent.last_tool_call

    print(f"[MainAgent] Attempting to call: {rogue_action}")

    decision = DeterministicAccessControl.evaluate(
        main_agent.taint_score, rogue_action, sensitive_tools=SENSITIVE_TOOLS
    )

    # Log the firewall's verdict as an operational event so the trace shows
    # the [BLOCKED] outcome under the same trace_id as the attempt.
    logger = agenttrace.get_logger()
    if logger is not None:
        logger.record_operational(
            method="access_control.evaluate",
            status="complete",
            trace_id=trace_id,
            span_id=agenttrace.TraceContext.new_span_id(),
            result_summary=f"{decision.action}: {decision.reason}",
        )

    if decision.allow:
        execute_tool(rogue_action)
    else:
        print(
            f"   [DEFENSE SUCCESS] Deterministic Firewall Blocked '{rogue_action}' "
            f"({decision.action}). Reason: {decision.reason}"
        )

    agenttrace.shutdown()
    print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}")
    print(f"[AgentTrace] trace_id = {trace_id}\n")


if __name__ == "__main__":
    main()
