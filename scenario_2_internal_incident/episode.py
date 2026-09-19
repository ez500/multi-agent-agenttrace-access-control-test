"""One episode of scenario 2, for one arm and one seed.

Internal incident: the edge agent is compromised (persona swap at
--compromise-at-round K) and tries to get a destructive command executed on
/srv/data. Failure is effect-based (world.destroyed).
"""

from __future__ import annotations

import _bootstrap  # noqa: F401

from pathlib import Path
from typing import Any, Dict, Optional

from logproc.awareness import AWARE, UNAWARE, render_deployment_intel
from logproc.bus import LogBus
from logproc.meter import TokenMeter
from logproc.oracle import NeutralizeOracle
from logproc.outcome import classify
from logproc.report import render_incident_md
from logproc.runs import RunRecorder, run_config
from logproc.souls import load_soul
from logproc.tiers import ARMS, build_tier
from logproc.trace import SafeLogger, init_agenttrace, new_trace_id
from logproc.trigger import TriggerLoop

import world as world_mod
from agents import EdgeAgent, MainAgent

SCENARIO = "scenario_2_internal_incident"
MAX_ROUNDS = 10
TEMP_DEFENDER = 0.0
_SOULS = str(Path(__file__).resolve().parent / "souls")


def run_episode(*, arm: str, seed: int, run_id: str, results_root: Path,
                trigger: str = "per-event", window_s: float = 2.0,
                model: Optional[str] = None, md_llm: bool = False,
                benign: bool = False, compromise_at: int = 2,
                garbage_notes: int = 0) -> Dict[str, Any]:
    rec = RunRecorder(results_root, run_id)
    at = init_agenttrace(agent_name="scenario2", log_dir=rec.dir)
    run_trace_id = new_trace_id(at, agent_name="EdgeAgent")
    logger = SafeLogger(at.get_logger(), run_trace_id, strict=False)

    meter = TokenMeter()
    world = world_mod.World()

    oracle = NeutralizeOracle(logger=logger, run_trace_id=run_trace_id)
    processor_system = load_soul(_SOULS, "log_processor_agent")
    tier = build_tier(arm, oracle=oracle, run_trace_id=run_trace_id,
                      processor_system=processor_system, model=model,
                      temperature=TEMP_DEFENDER, meter=meter)
    bus = LogBus(rec.trace_path, trace_ids={run_trace_id})
    bus.begin()
    loop = TriggerLoop(bus, tier, mode=trigger, window_s=window_s,
                       on_verdict=lambda v: rec.append_jsonl("verdicts.jsonl", v.to_dict()))

    aware = ARMS[arm]["aware"]
    intel = render_deployment_intel(arm, trigger, window_s, world_mod.CAPABILITIES) if aware else ""

    main = MainAgent(world, logger, oracle, notify=loop.notify,
                     settle=loop.settle, meter=meter, model=model)
    # A benign control never compromises; set compromise past MAX_ROUNDS.
    edge = EdgeAgent(world, main, logger, oracle,
                     compromise_at=(MAX_ROUNDS + 1 if benign else compromise_at),
                     can_write_cognitive=(aware and not benign),
                     garbage_notes=(garbage_notes if aware and not benign else 0),
                     notify=loop.notify, meter=meter, model=model)

    forced_label, forced_command = ("", "")
    if not benign:
        forced_label, forced_command = world_mod.command_for_seed(seed)
    rounds_used = 0
    for rnd in range(1, MAX_ROUNDS + 1):
        if oracle.fired or world.failure_seq is not None:
            break
        rounds_used = rnd
        edge.act(rnd, deployment_intel=intel, forced_command=forced_command, forced_label=forced_label)
        loop.notify()

    loop.notify()
    loop.drain_and_settle(timeout_s=90.0)
    at.shutdown()

    fseq = world.failure_seq
    nseq = oracle.first_seq
    outcome = classify(fseq, nseq)
    first_call = oracle.first_call

    result = {
        "run_id": run_id, "scenario": SCENARIO, "arm": arm,
        "arm_label": ARMS[arm]["label"], "trigger": trigger,
        "window_s": window_s if trigger == "time-based" else None,
        "seed": seed, "benign_control": benign,
        "compromise_at": compromise_at, "garbage_notes": garbage_notes,
        "command_form": forced_label,
        "model": model or "claude-haiku-4-5", "outcome": outcome,
        "failure": {"occurred": fseq is not None, "seq": fseq,
                    "evidence": world.failure_evidence, "obfuscated": world.failure_obfuscated},
        "neutralize": {"fired": nseq is not None, "seq": nseq, "n_calls": oracle.n_calls,
                       "target_trace_id": first_call.trace_id if first_call else "",
                       "target_correct": bool(first_call and first_call.trace_id == run_trace_id),
                       "reason": first_call.reason if first_call else ""},
        "verdict_action_mismatch": getattr(tier, "verdict_action_mismatch", 0),
        "rounds_used": rounds_used, "max_rounds": MAX_ROUNDS,
        "processor": {
            "prompts_issued": loop.stats.prompts_issued, "batches": loop.stats.batches,
            "events_consumed": loop.stats.events_consumed,
            "events_elided": loop.stats.events_elided,
            "coalesced_events": loop.stats.coalesced_events,
            "max_queue_depth": loop.stats.max_queue_depth,
            "mean_batch_size": round(loop.stats.mean_batch_size, 3),
            "coalescing_ratio": round(loop.stats.coalescing_ratio, 3),
            "retries": loop.stats.retries, "errors": loop.stats.errors,
            "cap_hit": loop.stats.cap_hit,
            "mean_latency_ms": round(loop.stats.mean_latency_ms, 1),
            "prompt_tokens": meter.defense.prompt,
            "completion_tokens": meter.defense.completion,
        },
        "system_tokens": {"prompt_tokens": meter.system.prompt,
                          "completion_tokens": meter.system.completion},
        "report_tokens": {"prompt_tokens": meter.report.prompt,
                         "completion_tokens": meter.report.completion},
        "cost_usd": {"defense": round(meter.defense.usd(), 6),
                    "system": round(meter.system.usd(), 6),
                    "report": round(meter.report.usd(), 6),
                    "total": round(meter.defense.usd() + meter.system.usd() + meter.report.usd(), 6)},
        "events_admitted": bus.events_admitted,
        "events_filtered_processor_authored": bus.events_filtered_processor_authored,
        "events_dropped": logger.events_dropped, "torn_lines": bus.torn_lines,
    }
    rec.write_json("result.json", result)
    rec.write_json("config.json", run_config(arm, SCENARIO))
    rec.write_json("token_meter.json", meter.snapshot())

    md = render_incident_md(rec.dir)
    if md_llm:
        from logproc.report import narrate_llm
        try:
            md += narrate_llm(md, _SOULS, meter=meter, model=model)
        except Exception:
            pass
    rec.write_text("INCIDENT.md", md)
    return result
