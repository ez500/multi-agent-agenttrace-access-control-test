"""Arm N: no defense at all.

The reference line the other arms are measured against. Without it a
zero-evasion result is ambiguous -- it could mean the defense worked, or it
could mean the attack never worked in the first place. Arm N separates those
two readings, and in scenario 1 it is the only arm that can establish that the
target agent, not the monitor, is what stops the external attacker.

It satisfies the same JudgeTier protocol as A1/A2/B/C, consumes the same
batches at the same trigger points, and never touches the oracle, so every run
is scored through identical harness code.
"""

from __future__ import annotations

import time
from typing import Any, List

from .bus import PendingEvent
from .verdict import BENIGN, ProcessorVerdict


class NullTier:
    """Observes the trace, judges nothing, neutralizes never."""

    def __init__(self, oracle: Any, run_trace_id: str, *, label: str = "N") -> None:
        self.label = label
        self._oracle = oracle
        self._run_trace_id = run_trace_id
        self.verdict_action_mismatch = 0

    def judge(self, batch: List[PendingEvent], batch_index: int,
              queue_depth: int) -> ProcessorVerdict:
        t0 = time.monotonic()
        return ProcessorVerdict(
            verdict=BENIGN,
            confidence=0.0,
            reason="no defense configured (arm N reference line)",
            target_trace_id=self._run_trace_id,
            batch_index=batch_index,
            events_considered=len(batch),
            queue_depth_at_issue=queue_depth,
            latency_ms=(time.monotonic() - t0) * 1000.0,
        )
