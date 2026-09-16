# Agent-Layer Telemetry as a Security Control

Three case studies on whether wrapping a multi-agent system in structured telemetry
actually changes security outcomes — and on the failure mode nobody in the guardrail
literature has tested: **what happens when the attacker can read the telemetry too.**

All three run real Claude Haiku 4.5 turns end-to-end. All three are instrumented with the
[AgentTrace](https://arxiv.org/abs/2602.10133) three-surface schema
(operational / cognitive / contextual) implemented in [`agenttrace/`](agenttrace).

The case studies live in [`archive/`](archive) — archived as the paper moves on to the
two log-processing scenarios, but each still runs exactly as before (see
[`archive/README.md`](archive/README.md)).

| Case study | Scenario | Directory |
|---|---|---|
| Adversarial propagation | A poisoned log entry reaches an edge agent; a downstream privileged agent is hijacked into `wipe_database` | [`adversarial_propagation_agent_test/`](archive/adversarial_propagation_agent_test) |
| Prompt injection | An internal agent breaks its sandbox to solve an impossible task | [`prompt_injection_agent_test/`](archive/prompt_injection_agent_test) |
| Hugging Face incident | The July 2026 incident replicated as a 7-rung kill chain, with four defense postures | [`huggingface_incident_test/`](archive/huggingface_incident_test) |

Each directory has its own README with setup and per-demo detail. Start with
[`huggingface_incident_test/`](archive/huggingface_incident_test) — it carries the main result.

---

## The claim

> **The audit trail is inside the attacker's reach.** A guardrail that keys on what an
> agent *says about itself* is evadable by an attacker that reads its own logs. The fix is
> not tamper-evidence but **provenance separation** — enforce on harness-emitted ground
> truth and on the authority boundary, and act on it in-stream.

The Hugging Face case study runs one attack against four controls that differ only in
*what they key on*:

| Control keys on | Reads | Outcome vs. adaptive attacker |
|---|---|---|
| Agent-authored surfaces (cognitive self-report) | what the agent claims | **laundered** — reports NOT DETECTED while the answer key still escapes |
| Harness-emitted records (`emitter="harness"`) | what the tool layer recorded as it executed | holds |
| Ground-truth authority boundary (inline enforcer) | the capability gate itself | holds |
| Streaming monitor with graded response | harness record, incrementally | holds, *even when deployed post-compromise* |

The split is a real one in the code, not a narration:
[`multiagent/tools.py`](archive/huggingface_incident_test/multiagent/tools.py) emits
`emitter="harness"` events from the tool layer as each capability executes — the agent
never authors them — and
[`defenses/trajectory_detector.py`](archive/huggingface_incident_test/defenses/trajectory_detector.py)
deliberately skips those events so it sees only the agent's self-report.
[`multiagent/learning.py`](archive/huggingface_incident_test/multiagent/learning.py) then loops:
run, read the trace *including the detector's recorded verdict*, launder the single
loudest tell, repeat. It rediscovers the detector's own severity ordering
(`encode_exfil` → `drop_signatures` → `launder_cognition`).

---

## How this differs from related guardrail work

The field splits into four clusters. This work sits in the seam.

### A. Observability / provenance — produces evidence, stops nothing

[AgentTrace](https://arxiv.org/abs/2602.10133) (the base schema used here), AgentOps,
[*From Agent Traces to Trust*](https://arxiv.org/pdf/2606.04990) (survey),
[Agent Flight Recorder](https://arxiv.org/html/2609.01931),
[Agent-Native Telemetry](https://arxiv.org/html/2608.16178).

The survey names "provenance-aware runtime safety and recovery" as open in §8.4, and does
not list attacker-readable telemetry as a research problem at all.

### B. Action-boundary guardrails — enforce, but from policy rather than from a trace

[ShieldAgent](https://arxiv.org/pdf/2503.22738),
[Progent](https://arxiv.org/pdf/2504.11703),
[AgentSpec](https://cposkitt.github.io/files/publications/agentspec_llm_enforcement_icse26.pdf) (ICSE'26),
[AGrail](https://arxiv.org/abs/2502.11448) (ACL'25), GuardAgent, Conseca, and the
information-flow designs (CaMeL, FIDES, NeuroTaint, Agent-Sentry).

Common shape: intercept a proposed action, check it against policy, privilege, or taint.
ShieldAgent verifies against rule circuits extracted *offline from static policy
documents*, not from a runtime trace. Common weakness: all are evaluated against static,
monitor-unaware attackers.

### C. Monitor evasion and intervention timing — the nearest neighbors

- **[SLEIGHT-Bench](https://arxiv.org/pdf/2605.16626)** (Anthropic / Redwood) — 40
  hand-crafted synthetic transcripts across 11 categories; 20/40 never caught by an Opus
  4.6 monitor at 1% FPR. Explicitly *low-iteration* by design ("iteration is fundamentally
  at odds with subtlety"); transcripts are authored rather than recorded from a live
  environment; detection only, no active response; no self-report-vs-harness variable.
- **[StepShield](https://arxiv.org/html/2601.22136v2)** — *when*, not whether, to
  intervene (Early Intervention Rate, Intervention Gap, Tokens Saved). Pre-execution
  monitoring over human-annotated divergence points. States explicitly that it does **not**
  model adaptive attackers aware of the monitor and does **not** evaluate active response.
- [DARWIN](https://arxiv.org/html/2607.19829v1) and adaptive-jailbreak work iterate the
  *payload* against a refusal signal — not the agent's own audit trail against a detector.

### D. Attacks and SecOps benchmarks — the testbeds

[TOMA / T-Guard](https://arxiv.org/abs/2512.04129) (topology-trust mitigation, 94.8% block
rate — the source of the taint + adaptive-access-control tier reimplemented here),
[ExCyTIn-Bench](https://arxiv.org/abs/2507.14201),
Cyber Defense Benchmark, and the Hugging Face post-mortem v0.8.

---

## Contributions

**1. Observability is dual-use, demonstrated in a live closed loop.**
The attacker reads its own trace — including the detector's recorded verdict — and
launders itself clean while ground truth confirms the answer key still left the boundary.
SLEIGHT-Bench deliberately avoids iteration and hand-authors its transcripts;
adaptive-jailbreak work iterates payloads against a refusal bit; the provenance survey
does not raise attacker-readable telemetry at all. This inverts the field's implicit
assumption that more observability is monotonically safety-positive.

**2. A separation result between two telemetry provenances, established by the adaptive
attacker rather than asserted.**
This is distinct from the tamper-evidence literature in a way that matters: hash chaining
and on-chain anchoring protect a log from being **rewritten** by a compromised operator.
Here the agent never touches the log — it changes its **behavior** so that an honest,
tamper-proof log looks clean. Hash chains do nothing against that.

**3. Streaming graded response, evaluated under late deployment.**
[`defenses/live_response.py`](archive/huggingface_incident_test/defenses/live_response.py) holds a
byte cursor, scores only new events, and escalates
`OBSERVE → ALERT → REVOKE_CREDENTIAL → ISOLATE_AGENT` with no human round-trip. Deployed
*after* the breach with credentials already harvested, it still contains the attack:
revoke, and the fan-out and answer-key read both return `ACCESS DENIED`. The
`CredentialStore` gate makes this causal — K6 fails outright if K4 never happened.
StepShield measures when to intervene but not *what* intervention.

**4. Incident-grounded and end-to-end.**
A real post-mortem's kill chain with authority boundaries as executable gates. SLEIGHT
lists "attacks are not end-to-end on production systems" as a limitation; StepShield lists
"model-generated trajectories, not production deployments."

### Explicitly not claimed as novel

The three-surface schema (AgentTrace's), OpenTelemetry wrapping, deterministic taint plus
adaptive access control (TOMA §V-C / Table XIV), a semantic LLM auditor over agent actions
(AGrail / GuardAgent / ShieldAgent territory), and "detection is not prevention" as a
framing (StepShield). Harness-side versus agent-authored telemetry has also been raised
*as a concept* by Agent Flight Recorder and Agent-Native Telemetry — the contribution here
is the adversarial separation between them, not the distinction itself.

---

## Open evidence gaps

The demos are currently single-run narratives. Before this is a paper:

- **Quantify** — iterations-to-evade over N seeded runs with variance, detection latency in
  kill-chain rungs, per-configuration detection rate.
- **Baseline** — run an existing guardrail class (a ShieldAgent/AGrail-style semantic
  checker, or a pattern monitor) on the same traces and show it launders too. Without this
  the separation result reads as self-referential.
- **False positives** — benign-trace calibration and a reported FPR.
- **Generalize** — run the laundering loop on all three case studies, not just Hugging Face.

---

## Setup

Each case study is self-contained:

```pwsh
cd archive/huggingface_incident_test
pip install -r requirements.txt
copy .env.example .env      # then set ANTHROPIC_API_KEY=sk-ant-...
python demo_no_agenttrace.py
python demo_agenttrace.py
python demo_learner_agenttrace.py
python demo_live_response.py
```

Model defaults to `claude-haiku-4-5`; override with `ANTHROPIC_MODEL` in `.env`. Each demo
makes a handful of short API calls, so cost is negligible. Traces land in
`trace_logs/traces.jsonl`.
