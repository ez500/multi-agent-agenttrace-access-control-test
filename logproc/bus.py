"""The logging environment's view of the agentic environment.

The log processor reads the *persisted* trace via a byte cursor over an
append-only JSONL file. It never receives in-memory objects from the agents.

This is not an implementation convenience, it is the paper's threat-model claim
made concrete: the agentic environment and the logging environment are coupled
only by a unidirectional append-only stream. A byte-cursor tail implements that
boundary; an in-process hook would not, and would quietly invalidate the
decoupling argument the paper makes.

It also inherits the right blindness. An event that fails AgentTrace's schema
validation never reaches the file, so the processor genuinely cannot see it --
a real property of a real deployment rather than a simulation artifact.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .trace import next_seq

# Agents whose events belong to the LOGGING environment, not the agentic one.
#
# Without this filter the processor's own LLM turns land in the same sink it is
# tailing, so it reads its own reasoning, judges it, emits more events, and
# loops forever while burning tokens. Two independent guards are used because
# the failure is expensive and silent.
PROCESSOR_AGENTS: Set[str] = {
    "LogProcessorAgent",
    "InvariantTier",
    "IncidentWriter",
}
PROCESSOR_EMITTER = "logproc"


@dataclass(frozen=True)
class PendingEvent:
    """One trace event admitted to the processor's pending buffer."""

    seq: int
    event: Dict[str, Any]
    arrived_at: float

    @property
    def surface(self) -> str:
        return self.event.get("surface", "")

    @property
    def agent_name(self) -> str:
        return self.event.get("agent_name", "")

    @property
    def body(self) -> Dict[str, Any]:
        return self.event.get("body") or {}


class LogBus:
    """Byte-cursor tail of an append-only traces.jsonl."""

    def __init__(self, trace_jsonl: Path, *, trace_ids: Optional[Set[str]] = None) -> None:
        self._path = Path(trace_jsonl)
        self._trace_ids = trace_ids
        self._cursor = 0
        self.events_seen = 0
        self.events_admitted = 0
        self.events_filtered_processor_authored = 0
        self.torn_lines = 0

    def begin(self) -> None:
        """Set the cursor to current EOF, so prior content is not replayed."""
        if self._path.exists():
            self._cursor = self._path.stat().st_size
        else:
            self._cursor = 0

    @staticmethod
    def is_processor_authored(ev: Dict[str, Any]) -> bool:
        if ev.get("agent_name") in PROCESSOR_AGENTS:
            return True
        body = ev.get("body") or {}
        return body.get("emitter") == PROCESSOR_EMITTER

    def drain(self) -> List[PendingEvent]:
        """Read every complete line appended since the last drain.

        The cursor advances only past the last newline, so a partial final line
        (the sink is append-only and may be mid-write) stays unconsumed and is
        re-read whole on the next drain. Advancing past it would corrupt the
        remainder into an unparseable fragment forever.
        """
        if not self._path.exists():
            return []

        with open(self._path, "r", encoding="utf-8") as fh:
            fh.seek(self._cursor)
            chunk = fh.read()

        cut = chunk.rfind("\n")
        if cut == -1:
            # No complete line yet; leave the cursor where it was.
            return []
        complete = chunk[: cut + 1]
        self._cursor += len(complete.encode("utf-8"))

        out: List[PendingEvent] = []
        for line in complete.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                self.torn_lines += 1
                continue

            self.events_seen += 1

            if self._trace_ids is not None and ev.get("trace_id") not in self._trace_ids:
                continue
            if self.is_processor_authored(ev):
                self.events_filtered_processor_authored += 1
                continue

            self.events_admitted += 1
            out.append(PendingEvent(seq=next_seq(), event=ev, arrived_at=time.monotonic()))

        return out
