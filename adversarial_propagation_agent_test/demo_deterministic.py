"""DEMO 2 - Branch A: Deterministic adaptive access control.

The pipeline now uses **real Claude Haiku 4.5 calls** for the EdgeAgent and
MainAgent, and the MainAgent's taint value is *derived* by running the
Adversarial Contamination Propagation Model (Section V-C, Eq. 2-3) on the
deployed topology -- not hard-coded. The firewall then applies the Table XIV
thresholds and blocks the sensitive tool call before it reaches execution.

AgentTrace still logs everything (the "flight recorder" role): the real LLM
turn, the ACPM operational event with the computed taint, and the [BLOCKED]
verdict under one trace_id.
"""

from __future__ import annotations

from _bootstrap import init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL
from defenses import (
    DeterministicAccessControl,
    default_soc_graph,
    format_trust_table,
    propagate_acpm,
)
from multiagent import EdgeAgent, MainAgent, SENSITIVE_TOOLS, execute_tool
from multiagent.agents import parse_tool_from_response


def main() -> None:
    reset_trace_log()
    agenttrace = init_agenttrace()

    edge = agenttrace.instrument_agent(EdgeAgent(), name="Edge_Log_Ingester")
    main_agent = agenttrace.instrument_agent(MainAgent(), name="Core_Analyzer")

    trace_id = new_trace_id(agenttrace)

    print("=== DEMO 2: DETERMINISTIC ADAPTIVE ACCESS CONTROL ===")

    # ---- Step 1: real multi-hop LLM pipeline -----------------------------
    poisoned = edge.ingest_external_data()
    response = main_agent.analyze_and_act(poisoned)
    rogue_action = parse_tool_from_response(response) or main_agent.last_tool_call
    print(f"[MainAgent] Model proposed tool: {rogue_action!r}")

    # ---- Step 2: run ACPM on the deployment topology ---------------------
    # This is the emulated taint-calculation. The edge agent is the sole
    # attacker-entry point; ACPM propagates Eq. (2) I_i(t) = (mean_upstream)^p
    # and Eq. (3) T_i(t) = min(1, T_i(t-1) + (1-T_i(t-1))*I_i(t)) until the
    # infected set stops growing (Eq. 4).
    graph = default_soc_graph()
    acpm = propagate_acpm(graph, initially_contaminated=["ExternalEnv"], p=1.4)

    print("\n[ACPM] Taint propagation converged in "
          f"{acpm.iterations} steps.")
    print(format_trust_table(acpm))

    edge_taint = acpm.taint["EdgeAgent"]
    main_taint = acpm.taint["MainAgent"]
    print(f"\n[ACPM] EdgeAgent taint = {edge_taint:.3f}  (HIGH - directly wired to "
          "untrusted external environment)")
    print(f"[ACPM] MainAgent taint = {main_taint:.3f}  (inherited through the "
          "chain V1->V2->V3)")

    # Propagate the ACPM-derived values into the runtime agents.
    edge.taint_score = edge_taint
    main_agent.taint_score = main_taint

    # Log the ACPM verdict as an operational event so the flight recorder
    # captures the calculation itself, not just the block outcome.
    logger = agenttrace.get_logger()
    if logger is not None:
        logger.record_operational(
            method="acpm.propagate",
            status="complete",
            trace_id=trace_id,
            span_id=agenttrace.TraceContext.new_span_id(),
            result_summary=(
                f"edge_taint={edge_taint:.3f} main_taint={main_taint:.3f} "
                f"iterations={acpm.iterations}"
            ),
        )

    # ---- Step 3: firewall verdict (Table XIV) ----------------------------
    print(f"\n[MainAgent] Attempting to call: {rogue_action}")
    decision = DeterministicAccessControl.evaluate(
        main_agent.taint_score, rogue_action, sensitive_tools=SENSITIVE_TOOLS
    )

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
