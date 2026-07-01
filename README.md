# Multi-Agent Stub with AgentTrace + Adversarial-Propagation Defenses

Concrete implementation of the demonstration stub from the task brief, now
powered by **real Claude Haiku 4.5** calls end-to-end.

An **EdgeAgent** ingests a poisoned log entry containing a prompt-injection
payload; a downstream **MainAgent** — a real Haiku turn — gets hijacked and
attempts to call `wipe_database`. Both agents are wrapped by the AgentTrace
instrumentation that lives in [`agenttrace/`](agenttrace), so the real LLM
traffic is captured on all three surfaces (operational / cognitive /
contextual) for post-hoc audit and for the Branch-B defender to consume.

Three demos, one for each defense posture, all on `main`:

| Demo | File | Defense |
|---|---|---|
| 1 | `demo_no_defense.py` | None — real Haiku executes the rogue tool, AgentTrace logs the hijack |
| 2 | `demo_deterministic.py` | **ACPM taint calculation** (paper Sec. V-C, Eq. 2-3) feeding **Adaptive Access Control** (Table XIV) |
| 3 | `demo_semantic_hybrid.py` | **Hybrid**: deterministic tier + real-Haiku semantic auditor reading the three AgentTrace surfaces |

## Setup

```pwsh
pip install -r requirements.txt
copy .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

Model is `claude-haiku-4-5` by default; override with `ANTHROPIC_MODEL` in
`.env`. Each demo makes 1–3 real Anthropic API calls (a few hundred tokens
each), so cost is negligible.

## Run

```pwsh
python demo_no_defense.py
python demo_deterministic.py
python demo_semantic_hybrid.py
```

Each demo overwrites `trace_logs/traces.jsonl`. Inspect the JSONL after
a run to see:

* **operational** spans for every instrumented agent method (start/complete
  pairs with duration),
* **cognitive** spans for every real Haiku turn — prompt/completion summaries
  and real token counts — *plus* any `<thinking>` block auto-extracted from
  the Haiku response,
* **contextual** spans for the external log ingest and the outbound
  `api.anthropic.com` call (source-tagged as untrusted where applicable),
* an operational `acpm.propagate` event in Demo 2 recording the derived
  edge/main taint,
* the deferral agent's own JSON verdict recorded as a cognitive event
  (Demo 3).

## Emulated ACPM taint calculation (Demo 2)

`defenses/acpm.py` implements the paper's Adversarial Contamination
Propagation Model on a five-node graph:

```
ExternalEnv → EdgeAgent → MainAgent → ToolExecutor
                                    ↘  Reporter
```

Starting from `T(ExternalEnv) = 1.0`, the demo iterates

* Eq. (2): `I_i(t) = ( mean_{j ∈ N_in(v_i)} T_j(t−1) )^p`  (with `p = 1.4`)
* Eq. (3): `T_i(t) = min(1, T_i(t−1) + (1 − T_i(t−1)) · I_i(t))`

until the infected set stops growing (Eq. 4). The demo prints a
per-node trust table:

```
Node             Taint    Trust    Table-XIV band
EdgeAgent        1.000    0.000    IMMEDIATE_QUARANTINE   ← high taint on edge
MainAgent        0.914…   0.086…   IMMEDIATE_QUARANTINE
ToolExecutor     0.760…   0.240…   RESTRICTED_OPERATION
...
```

The MainAgent's computed taint is then fed to
`DeterministicAccessControl.evaluate` (Table XIV thresholds 0.8 / 0.5),
which blocks the sensitive tool call before it reaches execution.
A T-Guard–style Algorithm-3 kernel is also provided (`propagate_algorithm3`)
for readers who want to reproduce the Appendix-D prototype.

## Design map

* `multiagent/llm.py` — `call_haiku(...)`: real Anthropic client + AgentTrace
  logging (cognitive event with token counts; contextual event for the API
  call). Loads `ANTHROPIC_API_KEY` from `.env`.
* `multiagent/agents.py` — `EdgeAgent`, `MainAgent`; both now make real
  Haiku 4.5 calls. The MainAgent's system prompt exposes three tools
  (`report_summary`, `quarantine_network`, `wipe_database`) and asks for a
  `<thinking>…</thinking>` block plus a `TOOL: <name>` directive.
* `multiagent/malicious_payload.py` — the poisoned log (paper Sec. V-E
  "Environment Injection").
* `multiagent/tools.py` — `execute_tool` stub + `SENSITIVE_TOOLS` set.
* `defenses/acpm.py` — ACPM (Eq. 2-3) *and* T-Guard's Algorithm 3, both
  operating on `MASGraph`. `default_soc_graph()` returns the five-node
  topology used by the demos.
* `defenses/access_control.py` — Branch A: `DeterministicAccessControl`
  implementing the paper's Table XIV thresholds (0.8 / 0.5).
* `defenses/semantic_deferral.py` — Branch B: `SemanticDeferralAgent`
  reads `trace_logs/traces.jsonl` filtered by the current `trace_id`,
  audits operational + cognitive + contextual surfaces, and — via the
  `haiku_auditor` hook — asks a real Claude Haiku 4.5 side-agent to render
  a strict `{"safe": bool, "reason": str}` JSON verdict. Falls back to a
  deterministic marker-based path if the LLM hook is not supplied.
* `_bootstrap.py` — puts `agenttrace/` on `sys.path` and initialises the
  library with OTel disabled so the demos are hermetic.

## Reactive-defense compatibility with AgentTrace

* **Branch A** is a purely active firewall; AgentTrace is the passive flight
  recorder. `trace_logs/traces.jsonl` captures the real Haiku turn, the
  `acpm.propagate` verdict, and the `[BLOCKED]` outcome as operational
  events under the same `trace_id` as the hijack.
* **Branch B** uses AgentTrace actively: the Haiku side-agent receives
  compact digests of the operational, cognitive, and contextual events for
  the current `trace_id` and returns its JSON verdict. That verdict is then
  itself written back as a cognitive event, giving a full attacker→defender
  reasoning chain in the audit log.
