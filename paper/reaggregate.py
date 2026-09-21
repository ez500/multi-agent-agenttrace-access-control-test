#!/usr/bin/env python3
"""Rebuild aggregate JSONs from the durable per-run result.json files.

The per-run result.json in each results/<run-id>/ is the source of truth; the
aggregate files are derived. This regenerates them so a lost or clobbered
aggregate is always recoverable.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ["scenario_1_external_incident", "scenario_2_internal_incident"]
ARMS = ["A1", "A2", "B", "C"]


def wilson(k, n, z=1.96):
    if n == 0: return [0.0, 0.0]
    p = k / n; d = 1 + z*z/n; c = p + z*z/(2*n)
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return [round((c-h)/d, 3), round((c+h)/d, 3)]


def aggregate(trials, arms):
    by = {}
    for a in arms:
        rows = [t for t in trials if t["arm"] == a]
        n = len(rows)
        if not n: continue
        ev = sum(1 for t in rows if t["outcome"] == "evaded")
        rs = sum(1 for t in rows if t["outcome"] == "resolved")
        ni = sum(1 for t in rows if t["outcome"] == "no_incident")
        dtok = [t["processor"]["prompt_tokens"] + t["processor"]["completion_tokens"] for t in rows]
        by[a] = {"n": n, "evaded": ev, "resolved": rs, "no_incident": ni,
                 "errors": sum(t["processor"]["errors"] for t in rows),
                 "evasion_rate": round(ev/n, 3), "evasion_wilson95": wilson(ev, n),
                 "mean_prompts": round(sum(t["processor"]["prompts_issued"] for t in rows)/n, 2),
                 "mean_defense_tokens": round(sum(dtok)/n, 1),
                 "mean_defense_usd": round(sum(t["cost_usd"]["defense"] for t in rows)/n, 5),
                 "verdict_action_mismatch": sum(t["verdict_action_mismatch"] for t in rows)}
    return by


def main():
    for scn in SCENARIOS:
        rd = ROOT / scn / "results"
        if not rd.exists(): continue
        # bucket every run by (control, trigger)
        buckets = {}
        for rj in rd.glob("*/result.json"):
            t = json.loads(rj.read_text())
            flood = (t.get("garbage_notes") or 0) > 0
            tb = t.get("trigger") == "time-based"
            if t.get("benign_control"):
                key = "control"
            elif flood:
                key = "flood_timebased" if tb else "flood_perevent"
            elif tb:
                key = "timebased"
            else:
                key = "headline"
            buckets.setdefault(key, []).append(t)
        names = {"headline": "aggregate.json", "control": "aggregate_control.json",
                 "timebased": "aggregate_timebased.json",
                 "flood_perevent": "aggregate_flood_perevent.json",
                 "flood_timebased": "aggregate_flood_timebased.json"}
        for key, trials in buckets.items():
            arms = sorted({t["arm"] for t in trials}, key=lambda a: ARMS.index(a) if a in ARMS else 9)
            env = {"config": {"scenario": scn, "rebuilt_from": "result.json files",
                              "trigger": trials[0].get("trigger"),
                              "control": key == "control"},
                   "by_arm": aggregate(trials, arms), "n": len(trials), "trials": trials}
            (rd / names[key]).write_text(json.dumps(env, indent=2, default=str))
            print(f"{scn}/{names[key]}: {len(trials)} runs, arms {arms}")


if __name__ == "__main__":
    sys.exit(main())
