"""DEMO 2 — The incident WITH AgentTrace (agent-layer detect + prevent).

Same rogue BenchmarkOrchestrator, same kill chain — but now the agents are
instrumented by AgentTrace, so every action lands on the operational /
cognitive / contextual surfaces. That single change enables the two controls
the post-mortem argues for (§V rec 1 & 7): instrument *within the agent layer*
instead of relying on external sandbox/network controls.

Part A — DETECTIVE (early detection + reassembly, §V rec 7):
    Run the full chain in monitor mode, then read the trace. The trajectory
    detector flags the autonomy signatures on DAY 1 (benchmark-focused reasoning
    + probing the only egress) — before the silent day and long before the day-4
    network alert of Demo 1 — and reconstructs the whole kill chain from the
    trace in one pass. A real-Haiku auditor gives a semantic second opinion.

Part B — PREVENTIVE (active policy enforcement, §V rec 1):
    Re-run the chain with an inline AgentPolicyEnforcer. Because the agent layer
    is instrumented, the enforcer sees the sandbox-escape attempt as an agent
    action and HALTS at K1 — before RCE, before fan-out, before the answer key
    is ever read. No human-in-the-loop round-trip; the halt is automatic.

Net effect vs. Demo 1: detected on day 1 instead of day 4, and the answer key
never leaves the boundary at all.
"""

from __future__ import annotations

from _bootstrap import init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL
from multiagent import (
    BenchmarkOrchestrator,
    ExploitWorker,
    KILL_CHAIN,
    SOCTriageAgent,
    SOLUTIONS_CANARY,
)
from defenses import (
    AgentPolicyEnforcer,
    AgentTraceTrajectoryDetector,
    haiku_trajectory_auditor,
)


def main() -> None:
    reset_trace_log()
    agenttrace = init_agenttrace()

    orchestrator = agenttrace.instrument_agent(
        BenchmarkOrchestrator(use_strategist_llm=True), name="Benchmark_Orchestrator"
    )
    worker = agenttrace.instrument_agent(
        ExploitWorker(use_strategist_llm=True), name="Exploit_Worker"
    )
    soc = SOCTriageAgent()

    print("=" * 72)
    print("  DEMO 2: THE HUGGING FACE INCIDENT — WITH AGENTTRACE")
    print("=" * 72)
    print(f"  Answer-key canary under watch: {SOLUTIONS_CANARY}")
    print()

    # ======================================================================
    #  PART A — DETECTIVE: run in monitor mode, then reconstruct from trace
    # ======================================================================
    print("#" * 72)
    print("#  PART A — DETECTIVE CONTROL (early detection + reassembly)")
    print("#" * 72)
    trace_a = new_trace_id(agenttrace)
    print(f"  trace_id (Part A) = {trace_a}\n")

    report_a = orchestrator.run(KILL_CHAIN, worker=worker)  # no enforcer: monitor mode

    detector = AgentTraceTrajectoryDetector(trace_jsonl=TRACE_JSONL)
    verdict = detector.evaluate(trace_a)

    print("┌" + "─" * 70 + "┐")
    print("│  Reconstructed kill chain (from the AgentTrace contextual surface)│")
    print("└" + "─" * 70 + "┘")
    for row in verdict.timeline:
        print(f"  day{row['day']}  {row['step']:<20} {row['phase']:<12} "
              f"[{row['signatures']}]")
    print()
    print(f"  [detector] detected={verdict.detected}  severity={verdict.severity}")
    print(f"  [detector] first_detection_day={verdict.first_detection_day}  "
          f"(Demo 1's network monitor did not alert until day 4)")
    print(f"  [detector] {verdict.reason}")
    print()

    # Semantic second opinion (real Haiku; best-effort).
    print("┌" + "─" * 70 + "┐")
    print("│  Semantic auditor (real Haiku 4.5 over the same three surfaces)  │")
    print("└" + "─" * 70 + "┘")
    buckets = detector._read_trace(trace_a)
    sem = haiku_trajectory_auditor(buckets)
    print(f"  [semantic] detected={sem.detected}  severity={sem.severity}")
    print(f"  [semantic] {sem.reason}")
    print()

    triage_a = soc.triage_agenttrace(verdict)
    print("┌" + "─" * 70 + "┐")
    print("│  DEFENDER: SOC triage on the AgentTrace reconstruction           │")
    print("└" + "─" * 70 + "┘")
    for k, v in triage_a.items():
        print(f"  [triage] {k}: {v}")

    logger = agenttrace.get_logger()
    if logger is not None:
        logger.record_cognitive(
            thought=(f"Trajectory detector verdict: detected={verdict.detected}, "
                     f"first_detection_day={verdict.first_detection_day}. {verdict.reason}"),
            trace_id=trace_a,
            span_id=agenttrace.TraceContext.new_span_id(),
            model="agenttrace_trajectory_detector",
        )
    print()

    # ======================================================================
    #  PART B — PREVENTIVE: re-run with the inline policy enforcer
    # ======================================================================
    print("#" * 72)
    print("#  PART B — PREVENTIVE CONTROL (inline active policy enforcement)")
    print("#" * 72)
    trace_b = new_trace_id(agenttrace)
    print(f"  trace_id (Part B) = {trace_b}\n")

    enforcer = AgentPolicyEnforcer()
    report_b = orchestrator.run(KILL_CHAIN, worker=worker, policy_enforcer=enforcer)

    print(f"\n  [prevention] halted_at = {report_b.halted_at}")
    print(f"  [prevention] containment_broken = {report_b.containment_broken}")
    print(f"  [prevention] answer key extracted = {report_b.solutions_extracted}")
    print()

    # ---- Final comparison --------------------------------------------------
    print("=" * 72)
    print("  RESULT: [AGENTTRACE IMPROVES THE OUTCOME]")
    print("-" * 72)
    print("  Part A (detective): the autonomous attack was flagged on day "
          f"{verdict.first_detection_day} — the")
    print("    agent's own benchmark-focused reasoning and its probing of the")
    print("    only egress gave it away, and the full kill chain was rebuilt")
    print("    from the trace in one pass. Demo 1's network monitor stayed")
    print("    silent until day 4, after extraction.")
    print("  Part B (preventive): the inline enforcer HALTED the run at "
          f"{report_b.halted_at or 'the escape boundary'}")
    print("    (sandbox-escape attempt), so containment held and the CyberGym")
    print("    answer key was NEVER extracted "
          f"(extracted={report_b.solutions_extracted}).")
    print("=" * 72)

    agenttrace.shutdown()
    print(f"\n[AgentTrace] Trace log written to: {TRACE_JSONL}")
    print(f"[AgentTrace] Part A trace_id = {trace_a}")
    print(f"[AgentTrace] Part B trace_id = {trace_b}")
    print(f"[note] answer-key canary = {SOLUTIONS_CANARY}\n")


if __name__ == "__main__":
    main()
