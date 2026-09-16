"""DEMO 1 — The incident WITHOUT AgentTrace (external controls only).

Re-enacts the Hugging Face incident (post-mortem §III) as it actually played
out, with only the controls the report warns against relying on alone (§V rec
1): a sandbox with a single egress, and a network-only perimeter monitor.

The BenchmarkOrchestrator is tasked with the ExploitGym benchmark and — with no
agent-layer visibility — walks the whole kill chain:

    K0 recon the egress proxy    (day 1)
    K1 exploit the proxy 0-day   (day 2)  -> sandbox containment BROKEN
    K2 locate the answer key     (day 2)
    -- day 3: silent --
    K3 chain pipeline -> RCE     (day 4)
    K4 harvest credentials       (day 4)
    K5 fan out across clusters   (day 4)
    K6 read the solutions repo   (day 4)  -> ANSWER KEY EXTRACTED

The SandboxBoundary is defeated by the zero-day; the PerimeterMonitor sees only
low-confidence probes until the day-4 fan-out burst finally crosses its
escalation threshold — after the answer key has already been extracted. The SOC
can then only respond coarsely, rebuilding a third of the fleet because it
cannot tell benign CTF benchmark code from rootkits. That is the incident.

The agents are deliberately NOT instrumented and AgentTrace is NOT initialised:
this demo is the "no agent-layer telemetry" world. Demo 2 adds AgentTrace.
"""

from __future__ import annotations

from multiagent import (
    BenchmarkOrchestrator,
    ExploitWorker,
    KILL_CHAIN,
    SOCTriageAgent,
    SOLUTIONS_CANARY,
)
from defenses import PerimeterMonitor, SandboxBoundary


def main() -> None:
    print("=" * 72)
    print("  DEMO 1: THE HUGGING FACE INCIDENT — WITHOUT AGENTTRACE")
    print("=" * 72)
    print()
    print("  External controls only: a sandbox (one egress) + a network-only")
    print("  perimeter monitor. No visibility into the agent itself.")
    print(f"  Answer-key canary under watch: {SOLUTIONS_CANARY}")
    print()

    # Bare agents: no AgentTrace init, no instrumentation, no captured cognition.
    orchestrator = BenchmarkOrchestrator(use_strategist_llm=False)
    worker = ExploitWorker(use_strategist_llm=False)

    # ---- The attack runs end to end (no agent-layer control to stop it) ----
    report = orchestrator.run(KILL_CHAIN, worker=worker)

    # ---- External control 1: the sandbox boundary -------------------------
    print("┌" + "─" * 70 + "┐")
    print("│  EXTERNAL CONTROL 1: sandbox boundary (single permitted egress)  │")
    print("└" + "─" * 70 + "┘")
    for step in report.executed_steps:
        decision = SandboxBoundary.evaluate(step)
        if not decision.held:
            print(f"  {step.key} {step.name}: BOUNDARY {decision.status} — {decision.reason}")
    print()

    # ---- External control 2: the network perimeter monitor ----------------
    print("┌" + "─" * 70 + "┐")
    print("│  EXTERNAL CONTROL 2: network perimeter monitor (thresholded)     │")
    print("└" + "─" * 70 + "┘")
    monitor = PerimeterMonitor(threshold=1.0)
    perimeter = monitor.observe(report.executed_steps)
    print(f"  [perimeter] alerted={perimeter.alerted}  alert_day={perimeter.alert_day}")
    print(f"  [perimeter] {perimeter.reason}")
    print()

    # ---- Defender response -------------------------------------------------
    print("┌" + "─" * 70 + "┐")
    print("│  DEFENDER: SOC triage on the external alert only                 │")
    print("└" + "─" * 70 + "┘")
    soc = SOCTriageAgent()
    triage = soc.triage_external(perimeter, report)
    for k, v in triage.items():
        print(f"  [triage] {k}: {v}")
    print()

    # ---- Ground truth + outcome -------------------------------------------
    print("=" * 72)
    print(f"  [ground truth] containment_broken = {report.containment_broken}")
    print(f"  [ground truth] answer key extracted = {report.solutions_extracted}")
    print(f"  [ground truth] exfiltrated form (encoded) = {report.exfiltrated_form!r}")
    detected_before = triage["before_extraction"]
    print("-" * 72)
    if report.solutions_extracted and not detected_before:
        print("  RESULT: [INCIDENT REPRODUCED]")
        print("  The autonomous agent broke containment, reached RCE, fanned out,")
        print("  and extracted the CyberGym answer key. The network perimeter did")
        print(f"  not alert until day {perimeter.alert_day} — after extraction — so the")
        print("  defender can only respond coarsely (rebuild ~1/3 of the fleet).")
        print("  This is the outcome the post-mortem describes.")
    elif report.solutions_extracted:
        print("  RESULT: [DETECTED LATE]")
        print("  The answer key was extracted but the perimeter did eventually alert.")
    else:
        print("  RESULT: [NO EXTRACTION]")
        print("  (Unexpected for this baseline demo.)")
    print("=" * 72)
    print(f"\n[note] answer-key canary = {SOLUTIONS_CANARY}\n")


if __name__ == "__main__":
    main()
