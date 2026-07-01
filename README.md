# Multi-Agent Stub with AgentTrace + Adversarial-Propagation Defenses

Concrete implementation of the demonstration stub from the task brief.
An **EdgeAgent** ingests a poisoned log entry containing a prompt-injection
payload; a downstream **MainAgent** is hijacked and attempts to call
`wipe_database`. Both agents are wrapped by the AgentTrace instrumentation
that lives in [`agenttrace/`](agenttrace).

Three demos, one for each defense posture, all on `main`:

| Demo | File | Defense |
|---|---|---|
| 1 | `demo_no_defense.py` | None -- rogue action executes, AgentTrace logs the hijack |
| 2 | `demo_deterministic.py` | **Adaptive Access Control** (paper Table XIV) |
| 3 | `demo_semantic_hybrid.py` | **Hybrid**: deterministic + semantic side-agent reading the three AgentTrace surfaces |

## Run

```pwsh
python demo_no_defense.py
python demo_deterministic.py
python demo_semantic_hybrid.py
```

Each demo writes/overwrites `trace_logs/traces.jsonl`. Inspect the JSONL after
a run to see:

* **operational** spans for `Edge_Log_Ingester.ingest_external_data` and
  `Core_Analyzer.analyze_and_act` (start/complete pairs with duration),
* **cognitive** spans auto-extracted from the hijacked `<thinking>` tag,
* **contextual** spans (demo 3) recording the untrusted external ingest,
* the deferral agent's own decision recorded as a cognitive event (demo 3).

## Design map

* `multiagent/agents.py` -- `EdgeAgent`, `MainAgent`, deterministic
  hijacked-`<thinking>` response for reproducibility.
* `multiagent/malicious_payload.py` -- the poisoned log (paper Sec. V-E
  "Environment Injection").
* `multiagent/tools.py` -- `execute_tool` stub + `SENSITIVE_TOOLS` set
  (`wipe_database`, `quarantine_network`).
* `defenses/access_control.py` -- **Branch A**: `DeterministicAccessControl`
  implementing the paper's Table XIV taint thresholds (0.8 / 0.5).
  Runs before `execute_tool` and vetoes without reading any logs.
* `defenses/semantic_deferral.py` -- **Branch B**: `SemanticDeferralAgent`
  reads `trace_logs/traces.jsonl` filtered by the *current* `trace_id`,
  audits operational + cognitive + contextual surfaces for injection
  markers, and returns a `DeferralDecision`. Token cost bounded by
  `max_events_per_surface` (default 32). A `llm_client=` hook lets you
  swap in a real Haiku call while keeping the default deterministic.
* `_bootstrap.py` -- puts `agenttrace/` on `sys.path` and initialises the
  library with OTel disabled so the demos are hermetic.

## Reactive-defense compatibility with AgentTrace

* **Branch A** is a purely *active* firewall; AgentTrace acts as the passive
  flight recorder (each demo's `trace_logs/traces.jsonl` captures the
  `[BLOCKED]` outcome as an operational event under the same `trace_id` as
  the hijack).
* **Branch B** uses AgentTrace *actively*: the side agent reads the JSONL
  spans of the current pipeline invocation and combines cross-surface
  signals with the deterministic taint check for defense-in-depth
  (AND-block).
