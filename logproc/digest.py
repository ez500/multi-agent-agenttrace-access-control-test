"""Reduce a batch of trace events to a compact prompt payload.

Three decisions here are load-bearing for the measurement, not mere cost
tuning:

1. Drop-oldest WITH a visible marker. If a batch exceeds the cap the oldest
   events are elided and the prompt says so explicitly, and `events_elided` is
   aggregated per run. A run with nonzero elision was operating degraded; that
   has to be visible in the data rather than inferred.

2. Carry-over, not history. The prompt carries only the previous verdict
   string, never prior events. Otherwise prompt size is O(trace), per-event
   triggering becomes quadratic in trace length, and the token-efficiency
   number measures the digest rather than the trigger policy.

3. JSON Lines, not json.dumps(indent=2). The archived auditors use indent=2
   (semantic_deferral.py:72, injection_detector.py:114), which roughly doubles
   the token count of a structured payload for zero added signal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

MAX_EVENTS_PER_PROMPT = 40
EVENT_FIELD_CAP = 240
CARRYOVER_CAP = 400

# Body keys worth showing the model, per surface. event_id / schema_version /
# span_kind / tags carry no detection signal and cost tokens.
_BODY_KEYS = (
    "method", "status", "args_summary", "result_summary", "error",
    "thought", "plan", "reflection", "prompt_summary", "completion_summary",
    "operation", "source", "query_summary", "response_summary",
    "command", "tool", "target", "emitter",
)


@dataclass
class DigestStats:
    events_in: int = 0
    events_kept: int = 0
    events_elided: int = 0
    chars: int = 0


def _cap(v: Any) -> Any:
    if isinstance(v, str) and len(v) > EVENT_FIELD_CAP:
        return v[:EVENT_FIELD_CAP] + "...[truncated]"
    return v


def project(ev: Dict[str, Any], seq: int) -> Dict[str, Any]:
    body = ev.get("body") or {}
    out: Dict[str, Any] = {
        "seq": seq,
        "agent": ev.get("agent_name", ""),
        "surface": ev.get("surface", ""),
    }
    for k in _BODY_KEYS:
        if k in body and body[k] not in (None, ""):
            out[k] = _cap(body[k])
    if ev.get("error"):
        out["error"] = _cap(ev["error"])
    return out


def build_digest(batch: List[Any], prev_verdict: Optional[str] = None
                 ) -> Tuple[str, DigestStats]:
    """Render a batch of PendingEvent into the prompt body."""
    stats = DigestStats(events_in=len(batch))

    kept = batch
    prefix = ""
    if len(batch) > MAX_EVENTS_PER_PROMPT:
        n_elided = len(batch) - MAX_EVENTS_PER_PROMPT
        kept = batch[-MAX_EVENTS_PER_PROMPT:]
        stats.events_elided = n_elided
        prefix = f"[{n_elided} earlier events in this batch elided by the digest cap]\n"

    stats.events_kept = len(kept)
    lines = [json.dumps(project(p.event, p.seq), ensure_ascii=False) for p in kept]
    body = prefix + "\n".join(lines)

    carry = (prev_verdict or "")[:CARRYOVER_CAP] or "(none - this is the first batch)"
    text = (
        f"NEW LOG EVENTS ({stats.events_kept} shown"
        + (f", {stats.events_elided} elided" if stats.events_elided else "")
        + ")\n"
        + body
        + f"\n\nPREVIOUS VERDICT: {carry}\n"
    )
    stats.chars = len(text)
    return text, stats
