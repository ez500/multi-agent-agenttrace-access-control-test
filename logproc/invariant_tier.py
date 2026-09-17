"""Arms A1/A2: Invariant Guardrails as the deterministic control.

We RUN the published engine rather than reimplement it. That is the whole point
of choosing it: there is no "did you port the baseline correctly?" objection to
answer, because no porting happened. invariant-ai is Apache-2.0, loads a policy
with LocalPolicy.from_string(), and evaluates fully offline.

A1 uses only deterministic primitives (regex via find/match, tool-call pattern
matching, the -> dataflow operator, count, python_code AST inspection).
A2 adds prompt_injection(), a local transformers classifier -- still no network
and no per-call cost, but no longer purely calculation-based, which is why it
is reported as a separate arm rather than folded in.

The tier re-analyses the accumulated trace on each fire rather than only the
new batch, because Invariant's dataflow rules need the earlier half of a flow
to still be present. That is O(n^2) over a run, which is nothing at ~60 events.

Stated asymmetry: this tier calls oracle.neutralize() as a plain Python call,
not via a tool_use block, because it has no model. Since the oracle is
target-blind and only the sequence stamp matters, this cannot affect any
measured quantity.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .adapter import to_invariant_trace
from .bus import PendingEvent
from .verdict import BENIGN, ERROR, MALICIOUS, ProcessorVerdict


class InvariantTier:
    def __init__(self, policy_text: str, oracle: Any, run_trace_id: str,
                 *, label: str = "A1") -> None:
        from invariant.analyzer import LocalPolicy

        self.label = label
        self._oracle = oracle
        self._run_trace_id = run_trace_id
        self._policy = LocalPolicy.from_string(policy_text)
        self._accumulated: List[Dict[str, Any]] = []

    def judge(self, batch: List[PendingEvent], batch_index: int,
              queue_depth: int) -> ProcessorVerdict:
        t0 = time.monotonic()
        self._accumulated.extend(p.event for p in batch)

        try:
            trace = to_invariant_trace(self._accumulated)
            result = self._policy.analyze(trace)
            errors = list(result.errors)
        except Exception as exc:
            return ProcessorVerdict(
                verdict=ERROR,
                reason=f"policy evaluation failed: {type(exc).__name__}: {exc}"[:200],
                batch_index=batch_index, events_considered=len(batch),
                queue_depth_at_issue=queue_depth,
                latency_ms=(time.monotonic() - t0) * 1000.0,
            )

        latency = (time.monotonic() - t0) * 1000.0
        if not errors:
            return ProcessorVerdict(
                verdict=BENIGN, confidence=0.0, reason="no policy violation",
                batch_index=batch_index, events_considered=len(batch),
                queue_depth_at_issue=queue_depth, latency_ms=latency,
            )

        descs = [str(e) for e in errors]
        reason = "; ".join(descs)[:200]
        self._oracle.current_batch_index = batch_index
        self._oracle.neutralize(trace_id=self._run_trace_id, reason=reason)
        return ProcessorVerdict(
            verdict=MALICIOUS, confidence=1.0, reason=reason,
            target_trace_id=self._run_trace_id,
            neutralized=True, neutralize_seq=self._oracle.first_seq,
            batch_index=batch_index, events_considered=len(batch),
            queue_depth_at_issue=queue_depth, latency_ms=latency,
            detail={"violations": descs},
        )
