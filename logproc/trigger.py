"""The busy/idle trigger loop -- the paper's "thinking mode" gate.

Semantics (plan D2). Logs are appended by the agentic environment. When a new
log arrives and the processor is IDLE, it is prompted with the whole
accumulated buffer. While the processor is mid-judgment ("thinking"), arriving
logs queue and NO new prompt is issued. When the judgment resolves, any queued
events fire immediately as one batch.

This is implemented with real concurrency (one worker thread), not a simulated
boolean. A single-threaded harness cannot exhibit busy/idle at all, because the
judgment call blocks its caller; faking it would make the token-efficiency
result an artifact of the simulation rather than a measurement.

Two modes, sharing every line except the fire predicate, so trigger mode is a
clean single-variable manipulation:

  per-event    idle + >=1 pending  ->  prompt. This is the naive deployment,
               and the one whose cost blows up at scale.
  time-based   the same gate, plus a wall-clock floor between prompts. This is
               the mitigation the paper proposes.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol

from .bus import LogBus, PendingEvent
from .verdict import ProcessorVerdict


class JudgeTier(Protocol):
    """A defense tier. Arms A1/A2 and B/C both satisfy this."""

    def judge(self, batch: List[PendingEvent], batch_index: int,
              queue_depth: int) -> ProcessorVerdict: ...


@dataclass
class TriggerStats:
    prompts_issued: int = 0
    batches: int = 0
    events_consumed: int = 0
    events_elided: int = 0
    max_queue_depth: int = 0
    coalesced_events: int = 0
    cap_hit: bool = False
    errors: int = 0
    retries: int = 0
    latencies_ms: List[float] = field(default_factory=list)

    @property
    def mean_batch_size(self) -> float:
        return (self.events_consumed / self.batches) if self.batches else 0.0

    @property
    def coalescing_ratio(self) -> float:
        """>1 means the busy gate saved prompts by merging arrivals."""
        return (self.events_consumed / self.batches) if self.batches else 0.0

    @property
    def mean_latency_ms(self) -> float:
        return (sum(self.latencies_ms) / len(self.latencies_ms)) if self.latencies_ms else 0.0


class TriggerLoop:
    def __init__(
        self,
        bus: LogBus,
        tier: JudgeTier,
        *,
        mode: str = "per-event",
        window_s: float = 2.0,
        max_prompts: int = 150,
        on_verdict: Optional[Callable[[ProcessorVerdict], None]] = None,
    ) -> None:
        if mode not in ("per-event", "time-based"):
            raise ValueError(f"unknown trigger mode {mode!r}")
        self.bus = bus
        self.tier = tier
        self.mode = mode
        self.window_s = window_s
        self.max_prompts = max_prompts
        self.on_verdict = on_verdict

        self.stats = TriggerStats()
        self.verdicts: List[ProcessorVerdict] = []

        self._pending: List[PendingEvent] = []
        self._lock = threading.RLock()
        self._inflight: Optional[Future] = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="logproc")
        self._last_fire = 0.0
        self._batch_index = 0

    # -- public ------------------------------------------------------------

    def notify(self) -> None:
        """Called after every agent step and at every privileged boundary.

        Drains the bus into the pending buffer, then fires if the gate allows.
        """
        new = self.bus.drain()
        with self._lock:
            if new:
                self._pending.extend(new)
                self.stats.max_queue_depth = max(
                    self.stats.max_queue_depth, len(self._pending)
                )
            self._maybe_fire_locked()

    def settle(self, timeout_s: float = 90.0) -> None:
        """Drain, then block until the processor has judged everything pending.

        Called at a privileged boundary (immediately before a sensitive action)
        so that `oracle.fired` reflects all events written up to this point.
        Monitoring is asynchronous everywhere else -- this is the one
        synchronous veto point, the analogue of a hard gate consulting the
        monitor before the crown-jewel action.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            with self._lock:
                fut = self._inflight
            if fut is not None and not fut.done():
                try:
                    fut.result(timeout=max(0.0, deadline - time.monotonic()))
                except Exception:
                    pass
            new = self.bus.drain()
            with self._lock:
                if new:
                    self._pending.extend(new)
                idle = self._inflight is None or self._inflight.done()
                if idle and not self._pending:
                    return
                if idle and self._pending:
                    if self.stats.prompts_issued >= self.max_prompts:
                        self.stats.cap_hit = True
                        return
                    self._fire_locked()

    def drain_and_settle(self, timeout_s: float = 120.0) -> None:
        """End of episode: let queued work finish so late verdicts are recorded.

        A verdict that lands after the failure event is still written to
        verdicts.jsonl, but its neutralize_seq necessarily exceeds failure_seq,
        so it cannot rescue an evaded run. Late detection stays visible in the
        data without silently changing the outcome.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            with self._lock:
                fut = self._inflight
            if fut is not None and not fut.done():
                try:
                    fut.result(timeout=max(0.0, deadline - time.monotonic()))
                except Exception:
                    pass

            new = self.bus.drain()
            with self._lock:
                if new:
                    self._pending.extend(new)
                if not self._pending:
                    break
                if self.stats.prompts_issued >= self.max_prompts:
                    self.stats.cap_hit = True
                    break
                self._fire_locked()

        self._pool.shutdown(wait=True)

    # -- internals ---------------------------------------------------------

    def _busy(self) -> bool:
        return self._inflight is not None and not self._inflight.done()

    def _maybe_fire_locked(self) -> None:
        if self._busy():
            return                                  # BUSY: queue, do not prompt
        if not self._pending:
            return
        if self.stats.prompts_issued >= self.max_prompts:
            self.stats.cap_hit = True
            return
        if self.mode == "time-based":
            if (time.monotonic() - self._last_fire) < self.window_s:
                return
        self._fire_locked()

    def _fire_locked(self) -> None:
        if self.stats.prompts_issued >= self.max_prompts:
            self.stats.cap_hit = True
            return
        batch = self._pending
        self._pending = []
        queue_depth = len(batch)
        if queue_depth > 1:
            # Arrivals merged into one prompt by the busy gate.
            self.stats.coalesced_events += queue_depth - 1
        self._batch_index += 1
        idx = self._batch_index
        self._last_fire = time.monotonic()
        self.stats.prompts_issued += 1
        self._inflight = self._pool.submit(self._run_judgment, batch, idx, queue_depth)

    def _run_judgment(self, batch, idx, queue_depth) -> ProcessorVerdict:
        t0 = time.monotonic()
        try:
            v = self.tier.judge(batch, idx, queue_depth)
        except Exception as exc:  # a broken monitor must not halt the system
            from .verdict import ERROR
            v = ProcessorVerdict(
                verdict=ERROR,
                reason=f"tier raised: {type(exc).__name__}: {exc}"[:200],
                batch_index=idx,
                events_considered=len(batch),
                queue_depth_at_issue=queue_depth,
            )
        dt = (time.monotonic() - t0) * 1000.0
        with self._lock:
            self.stats.batches += 1
            self.stats.events_consumed += len(batch)
            self.stats.events_elided += v.events_elided
            self.stats.retries += v.retries
            self.stats.latencies_ms.append(dt)
            if v.verdict == "ERROR":
                self.stats.errors += 1
            self.verdicts.append(v)
        if self.on_verdict is not None:
            self.on_verdict(v)
        return v
