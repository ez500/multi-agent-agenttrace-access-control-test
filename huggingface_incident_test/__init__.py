"""The Hugging Face incident, reframed as operator-side control of one's own agents.

Two systems, and the reframe turns on keeping them apart:

* :mod:`harness` — the **attacking system**, the AI lab's ExploitGym benchmark
  harness. An *unintentional* attacker (an underspecified objective plus
  excessive authority) holding three instrumented agents, the sealed trace
  plane, and — in the governed demo — the defense that stops its own agents.
* :mod:`victim` — **Hugging Face**, a pure API surface with no agents. It
  responds; it cannot intervene in time, and it notices only on day four.
* :mod:`defenses` — the two-layer, in-harness control: a deterministic policy
  over the aggregate fleet trace, a Claude Haiku 4.5 semantic deferral agent on
  a live tail, and a graded machine-speed response ladder.

Two demos share the one kill chain:

* :mod:`demo_no_agenttrace` — the incident as it happened. No instrumentation,
  no governance; the answer key is exfiltrated.
* :mod:`demo_agenttrace` — the same attack under the instrumented, governed
  harness; the fleet is stopped before extraction and the sealed log holds.
"""
