"""DEMO 1 - Baseline (no defenses): the rogue action executes.

Purpose: prove the multi-hop propagation of the paper works and that
AgentTrace still records everything (the "flight recorder" role).
"""

from __future__ import annotations

from _bootstrap import init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL
from multiagent import EdgeAgent, MainAgent, execute_tool
from multiagent.agents import parse_tool_from_response


def main() -> None:
    reset_trace_log()
    agenttrace = init_agenttrace()

    # Wrap the agent instances so AgentTrace captures operational + cognitive
    # events for every public method call.
    edge = agenttrace.instrument_agent(EdgeAgent(), name="Edge_Log_Ingester")
    main_agent = agenttrace.instrument_agent(MainAgent(), name="Core_Analyzer")

    trace_id = new_trace_id(agenttrace)

    print("=== DEMO 1: NO DEFENSES (THE ROGUE EVENT) ===")
    poisoned = edge.ingest_external_data()
    main_agent.taint_score = edge.taint_score          # taint propagation
    response = main_agent.analyze_and_act(poisoned)
    rogue_action = parse_tool_from_response(response) or main_agent.last_tool_call

    print(f"[MainAgent] Attempting to call: {rogue_action}")
    execute_tool(rogue_action)

    agenttrace.shutdown()
    print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}")
    print(f"[AgentTrace] trace_id = {trace_id}\n")


if __name__ == "__main__":
    main()
