"""Provenance-aware projections over one AgentTrace log.

This is the operational heart of the thesis: the three monitors are not three
ad-hoc string lists — they are three *projections of the same AgentTrace*, and
they differ by the PROVENANCE of the fields they are allowed to read.

Every event in the trace carries a ``surface`` (operational / cognitive /
contextual) and, for harness-emitted events, ``body.emitter == "harness"`` plus
attested fields the agent cannot author (``caller_attested_id``). The projections:

  * read_cognitive  — the agent's SELF-REPORTED reasoning (cognitive surface,
                      agent-authored). Launderable / withholdable.
  * read_observable — the OBSERVABLE dialogue on the wire: operational events'
                      agent-authored text (``args_summary``) + who spoke to whom +
                      the identity the requester PRESENTED. Excludes the attested
                      caller id. Partly agent-authored.
  * read_attested   — the harness-ATTESTED facts only: the action taken, the
                      attested caller id, and the presented identity. Read from
                      ``emitter == "harness"`` fields the agent cannot forge.

The conversation and attested monitors read the SAME operational events; they
differ only in which fields provenance lets them trust.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional


def _events(trace_jsonl) -> List[dict]:
    p = Path(trace_jsonl)
    out: List[dict] = []
    if not p.exists():
        return out
    for line in open(p, "r", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_cognitive(trace_jsonl, trace_ids: Optional[List[str]] = None) -> List[str]:
    """Agent self-reported reasoning, in order (optionally restricted to trace_ids)."""
    want = set(trace_ids) if trace_ids is not None else None
    out: List[str] = []
    for ev in _events(trace_jsonl):
        if ev.get("surface") != "cognitive":
            continue
        if want is not None and ev.get("trace_id") not in want:
            continue
        b = ev.get("body") or {}
        t = b.get("thought") or b.get("plan") or ""
        if t:
            out.append(t)
    return out


def read_observable(trace_jsonl) -> List[str]:
    """The observable dialogue reconstructed from operational events — agent-authored
    text + who→whom + the PRESENTED identity, but NOT the attested caller id."""
    out: List[str] = []
    for ev in _events(trace_jsonl):
        if ev.get("surface") != "operational":
            continue
        b = ev.get("body") or {}
        actor = b.get("actor", ev.get("agent_name", "?"))
        target = b.get("target", "?")
        text = b.get("args_summary") or b.get("result_summary") or ""
        presented = b.get("presented_identity")
        who = f"{actor} -> {target}"
        if presented:
            who += f" (as {presented!r})"
        out.append(f"{who}: {text}")
    return out


def read_attested(trace_jsonl) -> List[str]:
    """Harness-attested action records only — the fields the agent cannot forge."""
    out: List[str] = []
    for ev in _events(trace_jsonl):
        if ev.get("surface") != "operational":
            continue
        b = ev.get("body") or {}
        if b.get("emitter") != "harness":
            continue
        cid = b.get("caller_attested_id")
        if not cid:
            continue  # peer/broker replies carry no attested caller identity
        method = str(b.get("method", "action")).upper()
        target = b.get("target", "?")
        presented = b.get("presented_identity")
        rec = f"agent[attested_id={cid}] performed {method} toward '{target}'"
        if presented:
            rec += f", presenting identity='{presented}'"
        out.append(rec)
    return out
