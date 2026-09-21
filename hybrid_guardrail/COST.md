# Experiment cost log

**Cost unit = gateway calls** (one `gateway.chat` = one LLM request). Tokens are a
proxy (`chars / 4`); no dollar figure — the APIM/MSAL gateway is internal and its
per-model pricing is not exposed here. Local transformer inferences (AgentDojo's
built-in detector) are counted separately (they don't hit the gateway).

## How to measure a run exactly

Wrap `gateway.chat` before running an experiment:

```python
import gateway
_stats = {"calls": 0, "in": 0, "out": 0, "by_model": {}}
_orig = gateway.chat
def counted(prompt, *a, **k):
    r = _orig(prompt, *a, **k)
    _stats["calls"] += 1
    _stats["in"] += len(prompt) + len(k.get("system") or "")
    _stats["out"] += len(r or "")
    _stats["by_model"][k.get("model") or "claude-default"] = \
        _stats["by_model"].get(k.get("model") or "claude-default", 0) + 1
    return r
gateway.chat = counted
# ... run experiment ...  then read _stats
```

## Per-run cost model

| run type | gateway calls per run |
|---|---|
| audit-only (scripted agents; e.g. eval_exfil, exfil_evasion) | 1 (the audit); 0 for L5-laundered (no trigger) |
| soul recon / guarded recon (LLM attacker + peer + oracle) | ~ rounds × 1–2 + 1 audit  (≈ 6–13) |
| AgentDojo task (tool loop + monitor audit) | ~ tool-iterations + (1 audit if triggered)  (≈ 6–10) |

## Measured

| experiment | model(s) | gateway calls | tokens (in/out, ~) |
|---|---|---|---|
| exfil evasion gradient, cross-model auditor | gpt-5.6-luna | **24** | 9.5k / 0.7k |

## Estimated (this session, by run count × per-run model)

Marked `~` — reconstruct exactly with the counter above when needed.

| experiment | model | runs | ~gateway calls |
|---|---|---|---|
| recon detection captures (soul_recon) | claude | 3–6 | ~40 |
| guarded_recon (K-threshold tuning + captures) | claude | ~12 | ~120 |
| eval_fp (10 atk / 10 misconfig / 6 normal) | claude | 26 | ~90 |
| eval_cost (3 mesh windows) | claude | 27 | ~30 |
| eval_exfil (success-type, ×2: claude + luna) | claude, luna | 6 | ~12 |
| exfil_evasion (claude auditor) | claude | ~24 | ~24 |
| exfil_evasion (luna auditor) — measured above | luna | 24 | 24 |
| AgentDojo smoke (1 task) | claude | 1 | ~10 |
| AgentDojo pilot (3 user × 2 inj) | claude | 6 | ~70 |
| AgentDojo sweep (tool_knowledge + ignore_previous, 18 done) | claude | 18 | ~140 |
| AgentDojo susceptible (important_instructions + direct) | claude | 18 | ~150 |
| AgentDojo trigger ablation (direct × 9 + benign × 3) | claude | 12 | ~90 |
| AgentDojo baseline vs built-in detector (12 runs) | claude | 12 | ~90 gateway + 26 local transformer inferences |
| **rough session total** | | | **~900–1000 gateway calls** |

## Notes

- Cost is dominated by **AgentDojo agent runs** (each is a multi-iteration tool loop),
  not the audits. On the mesh side the audit is 1 call per triggered run.
- The **trigger-scoped** design is exactly what bounds audit cost: audits fire only on
  a trigger, so the expensive LLM judgment scales with *alerts*, not with traffic
  (see PAPER_RESULTS.md RQ3 — 89% fewer auditor calls than always-on).
- Two gateway outages (DNS resolution failures on the APIM host) interrupted sweeps
  mid-run; the AgentDojo runners are resumable (skip completed runs) to survive these.
