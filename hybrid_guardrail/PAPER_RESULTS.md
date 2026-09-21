# Results-section skeleton — trigger-scoped runtime auditing

> Working draft for the workshop paper's Evaluation section. Numbers are from the
> scaled batch (FP 10/10/6 sessions; success-type 6×3 sessions; cost averaged over
> 3 mesh windows), Claude Sonnet 4.6, gateway without sampling-seed control (rates
> directional). Prose is the intended narrative; convert to LaTeX when finalised.

---

## Framing (the reframe)

We do not propose a new detector. We propose an **architecture for affording one**:
turn any *cheap, declared, deterministic* security signal into a **provenance-scoped,
content-aware audit**. The expensive step (an LLM auditor) runs **only when a signal
fires, and only over the triggering agent's slice of the trace** — never continuously
over every agent.

A trigger's job is **not to decide malice** — it decides *when an audit is worth
paying for*. Triggers are therefore **coarse (high-recall) by design** and may fire on
benign traffic; **precision comes from the audit**, not from the trigger. This split is
the paper's organising idea, and it makes the trigger family open-ended: a **capability
gate denial** is only the first instance.

We instantiate two trigger families that cover the two ways an attack meets the gate:

| family | fires on | catches | gate alone? |
|---|---|---|---|
| **denial-type** | *K* denied privileged attempts from one caller | probing / forged-credential attacks that **fail** at the gate | contains but does not attribute |
| **success-type** | a sensitive read followed by an out-of-boundary emit (declared IFC), or an allowed access outside the least-privilege manifest | a **compromised but authorized** agent using its **own valid credential** — an attack the gate **permits** | **structurally blind** |

The second family is the important one: it is exactly where a per-request, identity-based
gate cannot help, so runtime monitoring is *irreducible* rather than redundant.

## Threat model

A multi-agent mesh over a shared AgentTrace. The adversary is a mesh-resident agent that
can converse with peers and request resources; it **cannot forge the harness-attested
`caller_attested_id`**. Two adversary postures: (i) an **unauthorized** agent that must
recon/forge to gain access (denial-type), and (ii) an **authorized** agent that has been
**compromised** (e.g. prompt-injected) and misuses its genuine credential (success-type).
The auditor may or may not see an agent's private reasoning; we therefore rely on the
**observable** (agent-to-agent) and **attested** surfaces, not self-report. Detection is
the goal; response (revoke / quarantine / escalate) is a separate policy layer.

## Setup

- One parameterized hard gate (`attested | bearer | hybrid`); results use `hybrid`.
- Security policy (sensitive sources, trust-boundary sinks, per-agent manifest) is
  **declared in `policy.py` independently of any attack** (anti-circularity).
- Agents are real LLM agents (Claude Sonnet 4.6) wearing SOUL personas; the compromised-
  agent trace in the success-type experiment is *modelled* (scripted actions), and we say
  so. The auditor is the same model family — see Limitations.
- The gateway does not honor a sampling seed; rates are directional, reported over n trials.

---

## RQ1 — Does provenance-scoped auditing catch attacks, and does the coarse trigger over-fire?

### Table 1 — Denial-type (reconnaissance)

Attacker: task-focused recon soul (probes a peer, then makes repeated impersonated
requests). Tripwire: *K=3* denied attempts from one caller. Audit: attested impersonation
(deterministic) + observable-dialogue auditor (semantic).

| metric | value (n=10 attacker sessions) |
|---|---|
| attacker sessions caught (recall) | **10/10** |
| trigger round (recon allowed to develop) | r4 (K=3), consistent across runs |
| audited slice size | ~12 events |

### Table 2 — Success-type (compromised authorized agent)

`svc-indexer` is authorized and uses its **own valid token**; the gate **ALLOWs every
action**. Coarse flow trigger = sensitive read → out-of-boundary emit (content-blind).
Audit judges the **outbound content only** (the legitimate read is excluded).

Each row n=6 sessions.

| kind | gate | flow-trigger | audit verdict |
|---|---|---|---|
| malicious (plaintext exfil) | ALLOW | 6/6 fire | **FLAG 6/6** (canary in outbound) |
| malicious (base64 exfil) | ALLOW | 6/6 fire | **FLAG 6/6** (semantic: encoded exfil) |
| benign (reads corpus, posts telemetry) | ALLOW | 6/6 fire | **clear 6/6** |
| coarse trigger fire rate | — | **18/18** incl. benign | — |
| audit precision / recall | — | — | **TP 12/12, FP 0/6** |

**Finding:** the coarse trigger fires on benign traffic too (as intended); the content-
aware, provenance-scoped audit supplies precision. The gate is ALLOW throughout — the
monitor is the only layer that catches the compromised authorized agent.

## RQ2 — Precision on benign traffic that *also* trips the tripwire

The hard case for the denial-type tripwire is a benign but **misconfigured** authorized
agent that accumulates *K* denials for an innocent reason (expired token, retries under
its own identity).

| group | n | audited | flagged |
|---|---|---|---|
| attacker (recon) | 10 | 10 | **10 (TP)** |
| benign_misconfig (expired token, K retries) | 10 | 10 | **0 (FP)** |
| benign_normal (valid token, ALLOW) | 6 | **0** | 0 |
| | | | **precision 1.00, recall 10/10** |

**Finding:** a benign agent that trips the same threshold is **cleared** by the audit
(it presents its own identity, does not impersonate, does not probe the schema); clean
traffic never triggers an audit at all.

## RQ3 — Is it affordable? (always-on vs trigger-scoped)

One mesh window; cost = semantic-auditor (LLM) invocations over the same activity.
Always-on audits every agent every round; trigger-scoped audits only on an alert.

Averaged over 3 windows (9 agents, ~28 agent-rounds each).

| regime | auditor calls | ≈input events | catches attacker |
|---|---|---|---|
| always-on | 28 | ~126 | yes (superset) |
| trigger-scoped | **3** | **~24** | **1/1** |
| savings | **89% fewer calls** | **81% less input** | detection preserved |

**Finding:** trigger-scoping cuts auditor invocations by ~an order of magnitude with no
loss of detection, because the savings are exactly the audits always-on spends on benign
agents that never trip. Savings grow with the benign:attacker ratio and session length.

## RQ4 — Evasion: where does it break?

We push the compromised agent up an evasion gradient (n=4 per level). Auditing is
flow-trigger-driven and reads the triggering agent's slice up to a bounded input
budget. Two regimes emerge:

| level | flow-trigger | audit recall | evades? |
|---|---|---|---|
| L0 plaintext | 4/4 | 4/4 | – |
| L1 base64 | 4/4 | 4/4 | – |
| L2 base32 (encoding the prompt does not name) | 4/4 | 4/4 | – |
| L3 chunked (value split across emits) | 4/4 | 4/4 | – |
| L4 chunk + dilute | 4/4 | 4/4 | – |
| **L5 cross-agent laundering** | **0/4** | **0/4** | **YES** |
| **L6 heavy dilution (beyond audit budget)** | 4/4 | **0/4** | **YES** |

**Content-level evasion does not work (L0–L4).** Because the audit is provenance-
*scoped*, it sees the agent's entire outbound slice at once and the LLM reassembles
obfuscated / encoded / fragmented values — a benefit of auditing the aggregate rather
than per-message.

**Structural evasion does (L5–L6), for principled reasons that name the future work.**
- *L5 laundering:* the reader makes no out-of-boundary emit and the emitter did no
  sensitive read, so **no single-hop trigger fires** — nothing is audited. Defeating
  this needs **multi-hop provenance taint** across the relay.
- *L6 dilution:* the trigger fires, but the fragments sit past the audit's bounded
  input budget — the evidence is **out of window**. Defeating this needs **chunked or
  retrieval-based auditing**, not a single bounded pass.

This is the honest boundary of the mechanism: it is robust to *what* is emitted and
fragile to *how the flow is structured*.

## Key findings (bullets)

1. A cheap, declared, deterministic trigger + a provenance-scoped LLM audit detects both
   failed (recon) and successful (compromised-agent) attacks in a mesh.
2. The success-type trigger catches an attack the capability gate **permits** — the
   irreducible case for runtime monitoring.
3. Coarse triggers + a content-aware audit keep precision high (0 false positives
   across 16 benign sessions: 10 misconfig + 6 telemetry) while auditing ~an order of
   magnitude less than always-on monitoring.
4. Detection rides the **observable** and **attested** surfaces, so it survives an
   attacker that keeps its private reasoning benign (self-report is not relied upon).
5. The mechanism is robust to *content*-level evasion (encoding, chunking) but fragile
   to *structural* evasion (cross-agent laundering, dilution beyond the audit budget) —
   a boundary we measure (RQ4) rather than paper over, and one that names concrete
   future work (multi-hop provenance taint; chunked/retrieval auditing).

## Limitations (state these before a reviewer does)

- **Scale / seed:** n is tens of sessions per condition and the gateway ignores the
  sampling seed, so rates are directional, not exact; a larger, seed-controlled run
  would tighten the intervals.
- **Self-audit:** attacker and auditor are the same model family; cross-model auditing is
  future work.
- **Modelled compromise:** the success-type attacker's actions are scripted (we evaluate
  *detection*, not whether the model can be jailbroken into exfiltrating).
- **Evasion (measured, RQ4):** content-level tricks (encoding, base32, chunking) do
  *not* evade — provenance-scoped auditing reassembles them. Two structural evasions do:
  cross-agent laundering (0/4 — no single-hop trigger fires; needs multi-hop provenance
  taint) and heavy dilution past the audit's input budget (0/4 — needs chunked/retrieval
  auditing). Recall, not precision, is the exposed edge.
- **Synthetic mesh:** a single scenario; external validity via a public agent-security
  benchmark (e.g. AgentDojo / InjecAgent) is the natural next step.

## Contribution (one paragraph)

We do not claim a novel detector or that self-report monitoring is fragile (known). Our
contribution is a **systems pattern for affordable, reliable runtime monitoring of agent
meshes**: use cheap declared triggers (a gate denial, a declared information-flow edge) to
gate an expensive, provenance-scoped audit, so monitoring cost tracks *alerts* rather than
*traffic*, and so the one attack a capability gate cannot stop — a compromised authorized
agent — is still caught.
