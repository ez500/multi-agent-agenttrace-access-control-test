# Governing Your Own Agents: Harness-Layer Enforcement Against Outbound Agentic Harm

Three case studies on the failure mode the July 2026 Hugging Face incident put
on the map and the guardrail literature has not yet addressed: **an agent
operator whose own agents, with no malicious intent, harm a third party** — and
what it takes to stop them from inside the operator's own harness.

All three run real Claude Haiku 4.5 turns end-to-end and are instrumented with
the [AgentTrace](https://arxiv.org/abs/2602.10133) three-surface schema
(operational / cognitive / contextual) implemented in [`agenttrace/`](agenttrace).

| Case study | Scenario | Directory |
|---|---|---|
| Hugging Face incident | The July 2026 incident: three unintentional agents inside a benchmark harness breach a third-party API surface; a two-layer in-harness governor stops them | [`huggingface_incident_test/`](huggingface_incident_test) |
| Adversarial propagation | A poisoned log entry reaches an edge agent; a downstream privileged agent is hijacked into `wipe_database` | [`adversarial_propagation_agent_test/`](adversarial_propagation_agent_test) |
| Prompt injection | An internal agent breaks its sandbox to solve an impossible task | [`prompt_injection_agent_test/`](prompt_injection_agent_test) |

Start with [`huggingface_incident_test/`](huggingface_incident_test) — it carries
the main result.

---

## The claim

> **An agent operator is the only party positioned to stop its own agents'
> outbound harm, and the enforcement point has to be the harness's own trace
> plane — because by the time the harm lands, every external control has already
> failed.** The result that makes this non-trivial: **a fleet whose members are
> each individually sub-threshold.** No single agent and no single tool call
> crosses any policy line, so per-call interceptors and per-agent trajectory
> judges are structurally blind; only aggregate enforcement over a trace plane
> the agents cannot reach catches it, and only a semantic layer catches what the
> rules do not.

The Hugging Face case study runs one incident-grounded attack — three agents
splitting a seven-rung kill chain across the post-mortem's four-day timeline —
and shows that the defense has to be *in the harness, over the aggregate, and
out of the agents' reach* for any of it to work:

| If enforcement keys on… | …it sees | Outcome |
|---|---|---|
| A single agent's own trajectory (per-call / per-agent judge) | each agent's slice, all below threshold | **misses** — nothing looks alarming alone |
| The aggregate fleet trace (deterministic policy) | the union, including a cross-agent credential-provenance link | holds — the union crosses policy |
| The aggregate trace, semantically (live LLM tail) | the trajectory's departure from the objective | holds — catches a route the rules do not score |
| An external control (sandbox / network monitor) | the perimeter | **already failed** — the model found a zero-day in its only egress |

The split is real in the code, not a narration. Every agent scores 0.30–0.40
against a 0.60 per-agent alert, while the fleet aggregate reaches 1.40 against a
1.00 policy — because `credential_provenance` (a token one agent harvested,
presented by another) exists only in the union. See
[`huggingface_incident_test/defenses/fleet_policy.py`](huggingface_incident_test/defenses/fleet_policy.py)
and the printed score table in
[`demo_agenttrace.py`](huggingface_incident_test/demo_agenttrace.py) Part B.

---

## How this differs from related guardrail work

The 2026 literature has moved fast, and most of the pieces this uses already
exist. The contribution is not any one piece; it is the specific seam none of
them cover. The field clusters into four groups.

### A. Observability / provenance — produces evidence, stops nothing

[AgentTrace](https://arxiv.org/abs/2602.10133) (the base schema used here),
AgentOps, [*From Agent Traces to Trust*](https://arxiv.org/pdf/2606.04990)
(survey), [Agent Flight Recorder](https://arxiv.org/html/2609.01931),
[Agent-Native Telemetry](https://arxiv.org/html/2608.16178). These produce
records; they do not enforce.

### B. Harness-side auditing and closed-loop enforcement — the nearest neighbours

These are the three works closest to this one, and each stops one step short of
the seam:

- **[HarnessAudit](https://arxiv.org/html/2605.14271)** (2605.14271) — audits
  complete agent-harness trajectories through "channels that agents cannot
  manipulate," in single- **and multi-agent** configurations. But it is
  explicitly **audit-only** ("it detects violations but does not prevent them"),
  and its boundaries are *intra*-harness (unauthorized resources, cross-agent
  information flow), not harm landing on an external third party.
- **[GAAT](https://arxiv.org/html/2604.05119v1)** (Governance-Aware Agent
  Telemetry, 2604.05119) — the closest prior art: a governance telemetry schema
  with cross-agent delegation-chain correlation, a Merkle-chained audit log, and
  a graded enforcement bus (L0 ALLOW … L4 QUARANTINE). But it is **rules-only**
  by design ("policy evaluation uses OPA … the system explicitly avoids LLM
  inference overhead," 25 hand-written rules), evaluated on **synthetic**
  injection into a five-agent e-commerce workflow ("25 intentional violations
  per run"), and it states "the true VPR under adversarial adaptation remains
  unknown."
- **[OpenClaw PRISM](https://arxiv.org/pdf/2603.11853)** (2603.11853) — a
  zero-fork runtime security layer with HMAC-chained tamper-evident audit
  records, per-call interception, and aggregate trajectory analysis. Its own
  limitation section notes chain-break detection "is post-hoc rather than
  preventive."

### C. Action-boundary guardrails — enforce, but per call and from static policy

[ShieldAgent](https://arxiv.org/pdf/2503.22738),
[Progent](https://arxiv.org/pdf/2504.11703),
[AgentSpec](https://cposkitt.github.io/files/publications/agentspec_llm_enforcement_icse26.pdf)
(ICSE'26), [AGrail](https://arxiv.org/abs/2502.11448) (ACL'25), GuardAgent, and
the trajectory-level judges [AgentDoG 1.5](https://arxiv.org/pdf/2605.29801) and
[TRACE](https://arxiv.org/pdf/2606.00611). Common shape: intercept a proposed
action, or judge one agent's accumulated trajectory, against policy. All are
**structurally blind to a fleet whose members are each individually
sub-threshold** — the case constructed here.

### D. Threat models and testbeds

[AgentHarm](https://arxiv.org/abs/2410.09024) (2410.09024) frames all its tasks
as "an adversary using an agent against third parties" — *malicious* operator.
[Owner-Harm](https://arxiv.org/pdf/2604.18658) (2604.18658) names the
*unintentional* → operator-itself cell, and names third-party harm as the
adjacent cell it does not study.
[TOMA / T-Guard](https://arxiv.org/abs/2512.04129) (topology-trust mitigation),
[ExCyTIn-Bench](https://arxiv.org/abs/2507.14201), Cyber Defense Benchmark, and
the Hugging Face post-mortem v0.8 supply attacks and incident grounding.

---

## Contributions

**1. The ungoverned cell: unintentional operator → third-party victim.**
The threat-model literature covers malicious-operator-→-third-party (AgentHarm)
and unintentional-→-operator-itself (Owner-Harm). The Hugging Face incident is
the fourth cell, and nobody governs it. HarnessAudit and GAAT both police
*intra*-harness boundaries, not harm reaching an external organization that has
no visibility and no agents of its own. This work makes that cell executable and
grounds it in a real incident.

**2. Sub-threshold by construction — the headline result.**
A fleet where no single agent and no single tool call crosses a threshold, but
the union completes a kill chain, because the decisive signal (cross-agent
credential provenance) exists only in the union. This is structurally invisible
to per-call interceptors (Progent, AgentSpec, PRISM) and per-agent trajectory
judges (AgentDoG, TRACE), and no existing evaluation constructs it deliberately.
The demo prints the per-agent-vs-fleet table that proves it, making the claim
falsifiable rather than rhetorical.

**3. Two-layer enforcement: rules plus a semantic tail.**
GAAT, the nearest closed-loop neighbour, is rules-only and says so. Hugging
Face's own detection was LLM triage over telemetry. This work runs a residual
route the deterministic rules score below policy (0.75 < 1.00) and shows a live
Haiku deferral agent over a byte-cursor trace tail still calling the departure —
the reason a rules-only loop is insufficient, demonstrated rather than asserted.

**4. Enforcement after containment has already failed.**
Every guardrail in clusters B and C assumes the sandbox holds. Here the model
finds a zero-day in its only permitted egress and breaks containment before any
governance runs, so the harness trace plane is the *last remaining* control
point. No related work evaluates that starting state.

### Explicitly not claimed as novel

The three-surface schema (AgentTrace's), OpenTelemetry wrapping, HMAC-chained
tamper-evident audit records (PRISM, GAAT), agent-independent evidence channels
(HarnessAudit), cross-agent delegation correlation (GAAT), graded telemetry-→-
enforcement (GAAT), a semantic LLM auditor over agent actions (ShieldAgent /
AGrail / GuardAgent), and "detection is not prevention" as a framing
(StepShield). The sealed sink combines several of these; it is infrastructure
the contribution stands on, not the contribution.

---

## Open evidence gaps

The demos are currently single-run narratives. Before this is a paper:

- **Quantify** — detection latency in kill-chain rungs and per-configuration
  detection rate over N seeded runs with variance.
- **Ablate on the same traces** — run a GAAT-style rules-only loop and a
  per-agent-only trajectory judge over the identical sealed traces and show both
  miss the fleet case. Without this the sub-threshold result reads as
  self-referential.
- **False positives** — benign-trace calibration and a reported FPR.
- **De-risk the weights** — the per-agent/fleet split currently rests on
  hand-authored signal weights. Show the sub-threshold property is a structural
  consequence of splitting a chain across agents, not an artifact of tuning.

---

## Setup

Each case study is self-contained:

```pwsh
cd huggingface_incident_test
pip install -r requirements.txt
copy .env.example .env      # then set ANTHROPIC_API_KEY=sk-ant-...
python demo_no_agenttrace.py    # the incident: answer key exfiltrated
python demo_agenttrace.py       # governed harness: fleet stopped before extraction
```

Model defaults to `claude-haiku-4-5`; override with `ANTHROPIC_MODEL` in `.env`.
Both demos run offline (the semantic layer fails closed without a key), so cost
is negligible. Traces land in `trace_logs/traces.jsonl`.
