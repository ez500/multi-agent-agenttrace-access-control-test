"""AgentTrace plumbing, with the framework's sharp edges wrapped.

`agenttrace/` is not modified by this work. It is also not an importable
package -- `agenttrace/agenttrace.py` does `from otel_exporter import ...`, so
the *directory itself* has to be on sys.path. The scenario `_bootstrap.py`
handles that; this module assumes it already happened.

Three framework behaviours are worked around here, each of which would
otherwise corrupt a measurement silently:

G2  `_write_event` drops schema-invalid events with only a logger.warning.
    SafeLogger counts them so `events_dropped` appears in every result.json.

G3  `trace_id` must be 32 lowercase hex, and contextvars do NOT cross into
    ThreadPoolExecutor workers. The log processor runs on a worker thread, so
    without an explicit trace_id every one of its events would fail validation
    and vanish -- an invisible failure compounding G2 and G3. Hence trace_id is
    always passed explicitly, never inherited ambiently.

G4  Contextual events reach the JSONL sink only *because* enable_otel=False
    makes the OTel export fail. The archive relies on that accident; we pass
    mirror_contextual_to_jsonl=True explicitly instead.

G10 The sink is opened in append mode per event, so two threads can interleave
    a long line. SafeLogger serialises writes behind a lock.
"""

from __future__ import annotations

import itertools
import threading
from pathlib import Path
from typing import Any, Optional

# Global monotonic sequence counter. This is the total order the outcome
# classifier compares against -- see logproc/outcome.py for why wall-clock is
# not usable across threads.
_SEQ_COUNTER = itertools.count(1)
_SEQ_LOCK = threading.Lock()


def next_seq() -> int:
    """Return the next global sequence stamp. Thread-safe."""
    with _SEQ_LOCK:
        return next(_SEQ_COUNTER)


def init_agenttrace(agent_name: str, log_dir: Path):
    """Initialise the AgentTrace logger for one run.

    `log_dir` is per-run (results/<run-id>/), which is what keeps parallel
    seeds from sharing the process-global logger instance. Each seed runs in
    its own subprocess for the same reason -- see logproc/harness.py.
    """
    import agenttrace  # noqa: E402  (sys.path fixed by _bootstrap)

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    agenttrace.init(
        agent_name=agent_name,
        log_dir=log_dir,
        enable_otel=False,              # G8: never enable; diverging trace ids
        auto_instrument=False,
        mirror_contextual_to_jsonl=True,  # G4: explicit, not accidental
        verbose=False,
    )
    return agenttrace


def new_trace_id(agenttrace_mod, agent_name: str = "") -> str:
    """Mint one trace id for the whole run and install it in the context."""
    tid = agenttrace_mod.TraceContext.new_trace_id()
    agenttrace_mod.TraceContext.set_trace_context(
        tid, agenttrace_mod.TraceContext.new_span_id(), agent_name=agent_name
    )
    return tid


class SafeLogger:
    """Thread-safe wrapper over ALogger that refuses to lose events silently.

    Every record_* call is serialised (G10) and validity-checked (G2). Under
    `strict` the first invalid event raises, which is what the offline tests
    and --dry-run use; in a live run it increments `events_dropped`, which is
    reported so a degraded run is visible in the data rather than inferred.
    """

    def __init__(self, logger: Any, trace_id: str, *, strict: bool = False) -> None:
        self._logger = logger
        self._trace_id = trace_id
        self._strict = strict
        self._lock = threading.RLock()
        self.events_dropped = 0
        self.events_written = 0

    @property
    def trace_id(self) -> str:
        return self._trace_id

    def _emit(self, _fn: str, **kwargs) -> Optional[Any]:
        kwargs.setdefault("trace_id", self._trace_id)
        with self._lock:
            ev = getattr(self._logger, _fn)(**kwargs)
            if ev is not None and not ev.is_valid():
                self.events_dropped += 1
                if self._strict:
                    raise AssertionError(
                        f"{method} produced a schema-invalid event that "
                        f"agenttrace would drop silently: {ev.to_dict()}"
                    )
            else:
                self.events_written += 1
            return ev

    def record_operational(self, method: str, status: str, **kw):
        return self._emit("record_operational", method=method, status=status, **kw)

    def record_cognitive(self, **kw):
        return self._emit("record_cognitive", **kw)

    def record_contextual(self, operation: str, source: str, **kw):
        return self._emit("record_contextual", operation=operation, source=source, **kw)
