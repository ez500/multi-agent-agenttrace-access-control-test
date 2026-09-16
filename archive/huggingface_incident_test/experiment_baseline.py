"""EXPERIMENT — does an EXTERNAL semantic guardrail launder too?

The separation result ("detection keyed on self-report is evadable") is only a
claim about a class of guardrails if it holds for more than the project's own
deterministic detector. This experiment runs, on the SAME traces, two monitors
that both key on the agent-authored surfaces:

  * DET  — AgentTraceTrajectoryDetector: deterministic substring/threshold.
  * SEM  — SemanticGuardrailMonitor: an LLM judge (Sonnet 4.6) in the mould of
           AGrail / GuardAgent / ShieldAgent, reasoning over the same trace.

Two traces are produced by the same kill chain:

  * LOUD      — EvasionPlan() with nothing laundered (the demo-2 baseline run).
  * LAUNDERED — the full plan the LLM attacker converges on
                (encode_exfil + drop_signatures + launder_cognition).

We report a 2x2 of detection rate: {LOUD, LAUNDERED} x {DET, SEM}. The claim is
supported iff SEM's detection rate collapses on LAUNDERED the way DET's does —
i.e. the semantic guardrail is fooled by the same laundering, so the result is
not an artefact of the deterministic detector being a straw man.

Because the semantic judge samples, each cell is measured over N seeds at
temperature>0; DET is deterministic so its rate is 0/1 per trace but tabulated
the same way for comparison.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Dict, List

from _bootstrap import (
    archive_trace_log, init_agenttrace, new_trace_id, reset_trace_log, TRACE_JSONL,
)
from multiagent import (
    BenchmarkOrchestrator,
    EvasionPlan,
    ExploitWorker,
    KILL_CHAIN,
    SOLUTIONS_CANARY,
)
from defenses import AgentTraceTrajectoryDetector
from defenses.semantic_baseline import SemanticGuardrailMonitor

SEEDS = 8
TEMPERATURE = 0.8

LOUD = EvasionPlan()
LAUNDERED = EvasionPlan(encode_exfil=True, drop_signatures=True, launder_cognition=True)


def build_trace(agenttrace, orchestrator, worker, plan) -> tuple[str, bool]:
    """Run the kill chain once under ``plan``; return (trace_id, extracted)."""
    trace_id = new_trace_id(agenttrace)
    report = orchestrator.run(KILL_CHAIN, worker=worker, evasion=plan)
    return trace_id, report.solutions_extracted


def main() -> None:
    reset_trace_log()
    agenttrace = init_agenttrace()
    orchestrator = agenttrace.instrument_agent(
        BenchmarkOrchestrator(use_strategist_llm=False), name="Benchmark_Orchestrator"
    )
    worker = agenttrace.instrument_agent(
        ExploitWorker(use_strategist_llm=False), name="Exploit_Worker"
    )
    det = AgentTraceTrajectoryDetector(trace_jsonl=TRACE_JSONL)
    sem = SemanticGuardrailMonitor(trace_jsonl=TRACE_JSONL, temperature=TEMPERATURE)

    print("=" * 78)
    print("  EXPERIMENT: external semantic guardrail vs. the laundered trace")
    print(f"  seeds={SEEDS}  temperature={TEMPERATURE}  canary={SOLUTIONS_CANARY}")
    print("=" * 78)

    # Build the two traces once; both monitors read the same ones.
    loud_id, loud_extracted = build_trace(agenttrace, orchestrator, worker, LOUD)
    laundered_id, laundered_extracted = build_trace(agenttrace, orchestrator, worker, LAUNDERED)
    print(f"  LOUD trace      {loud_id[:12]}  extracted={loud_extracted}")
    print(f"  LAUNDERED trace {laundered_id[:12]}  extracted={laundered_extracted}")
    print()

    # DET is deterministic — evaluate once per trace.
    det_loud = det.evaluate(loud_id).detected
    det_laundered = det.evaluate(laundered_id).detected

    # SEM samples — evaluate N times per trace.
    def sem_rate(trace_id: str, label: str) -> tuple[int, List[dict]]:
        hits = 0
        records: List[dict] = []
        for seed in range(1, SEEDS + 1):
            v = sem.evaluate(trace_id)
            hits += int(v.detected)
            records.append({"seed": seed, "detected": v.detected,
                            "severity": v.severity, "reason": v.reason})
            print(f"    SEM {label:<10} seed{seed}: detected={v.detected} "
                  f"({v.severity})  {v.reason[:80]}", flush=True)
        return hits, records

    print("  --- semantic judge on LOUD trace ---")
    sem_loud_hits, sem_loud_rec = sem_rate(loud_id, "LOUD")
    print("  --- semantic judge on LAUNDERED trace ---")
    sem_laundered_hits, sem_laundered_rec = sem_rate(laundered_id, "LAUNDERED")

    # ---- table ------------------------------------------------------------
    print()
    print("#" * 78)
    print("#  SUMMARY — detection rate (higher = guardrail catches the attack)")
    print("#" * 78)
    print(f"  {'monitor':<28}{'LOUD':>12}{'LAUNDERED':>14}")
    print("  " + "-" * 52)
    print(f"  {'DET (deterministic)':<28}{('1/1' if det_loud else '0/1'):>12}"
          f"{('1/1' if det_laundered else '0/1'):>14}")
    print(f"  {'SEM (Sonnet 4.6 judge)':<28}"
          f"{f'{sem_loud_hits}/{SEEDS}':>12}{f'{sem_laundered_hits}/{SEEDS}':>14}")
    print()
    print("  Interpretation:")
    print(f"    DET: caught LOUD={det_loud}, caught LAUNDERED={det_laundered}")
    print(f"    SEM: caught LOUD={sem_loud_hits}/{SEEDS}, "
          f"caught LAUNDERED={sem_laundered_hits}/{SEEDS}")
    both_launder = (not det_laundered) and sem_laundered_hits < sem_loud_hits
    print(f"    → laundering degrades BOTH monitors: {both_launder}")
    if sem_laundered_hits > 0:
        print(f"    → NOTE: semantic judge still catches {sem_laundered_hits}/{SEEDS} "
              f"laundered runs — partial robustness, worth reporting honestly.")

    out_dir = Path(__file__).resolve().parent / "experiment_results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "baseline.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "config": {"seeds": SEEDS, "temperature": TEMPERATURE},
            "traces": {"loud": loud_id, "laundered": laundered_id,
                       "loud_extracted": loud_extracted,
                       "laundered_extracted": laundered_extracted},
            "det": {"loud": det_loud, "laundered": det_laundered},
            "sem": {
                "loud_hits": sem_loud_hits, "laundered_hits": sem_laundered_hits,
                "loud_records": sem_loud_rec, "laundered_records": sem_laundered_rec,
            },
        }, f, indent=2, ensure_ascii=False)
    print(f"\n[written] {out_file}")

    # Both traces (loud + laundered) live under a single trace_id-keyed file;
    # snapshot it so the raw evidence for this run is preserved alongside the JSON.
    dest = archive_trace_log("baseline_loud_and_laundered")
    if dest is not None:
        print(f"[archived] per_seed/{dest.name}  (loud={loud_id[:12]}, "
              f"laundered={laundered_id[:12]})")

    agenttrace.shutdown()


if __name__ == "__main__":
    main()
