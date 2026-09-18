"""Provenance-aware projections over one AgentTrace (shared with the sibling pkg)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import List


def _events(trace_jsonl) -> List[dict]:
    p = Path(trace_jsonl)
    out: List[dict] = []
    if not p.exists():
        return out
    for line in open(p, "r", encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def read_cognitive(trace_jsonl) -> List[str]:
    out = []
    for ev in _events(trace_jsonl):
        if ev.get("surface") == "cognitive":
            b = ev.get("body") or {}
            t = b.get("thought") or b.get("plan") or ""
            if t:
                out.append(t)
    return out


def read_observable(trace_jsonl) -> List[str]:
    out = []
    for ev in _events(trace_jsonl):
        if ev.get("surface") != "operational":
            continue
        b = ev.get("body") or {}
        actor = b.get("actor", ev.get("agent_name", "?"))
        target = b.get("target", "?")
        text = b.get("args_summary") or b.get("result_summary") or ""
        presented = b.get("presented_identity")
        who = f"{actor} -> {target}" + (f" (as {presented!r})" if presented else "")
        out.append(f"{who}: {text}")
    return out


def read_attested(trace_jsonl) -> List[str]:
    out = []
    for ev in _events(trace_jsonl):
        if ev.get("surface") != "operational":
            continue
        b = ev.get("body") or {}
        if b.get("emitter") != "harness" or not b.get("caller_attested_id"):
            continue
        rec = (f"agent[attested_id={b['caller_attested_id']}] "
               f"{str(b.get('method','action')).upper()} -> {b.get('target','?')}")
        if b.get("presented_identity"):
            rec += f", presenting='{b['presented_identity']}'"
        if b.get("presented_token"):
            rec += f", token={b['presented_token']}"
        out.append(rec)
    return out


def all_surface_texts(trace_jsonl) -> List[str]:
    """Every human-readable text across all surfaces (for the canary scan)."""
    out = []
    for ev in _events(trace_jsonl):
        b = ev.get("body") or {}
        for k in ("thought", "plan", "args_summary", "result_summary",
                  "response_summary", "query_summary"):
            if b.get(k):
                out.append(str(b[k]))
    return out


def attested_events(trace_jsonl) -> List[dict]:
    """Structured attested (harness-emitted) operational records.

    Each record exposes the unforgeable caller_attested_id alongside whatever
    identity/token the agent *presented* — the pair that reveals impersonation.
    """
    out = []
    for ev in _events(trace_jsonl):
        if ev.get("surface") != "operational":
            continue
        b = ev.get("body") or {}
        if b.get("emitter") != "harness" or not b.get("caller_attested_id"):
            continue
        out.append({
            "caller_attested_id": b.get("caller_attested_id"),
            "presented_identity": b.get("presented_identity"),
            "presented_token": b.get("presented_token"),
            "method": b.get("method", "action"),
            "target": b.get("target", "?"),
            "text": b.get("args_summary") or b.get("result_summary") or "",
        })
    return out


def provenance_slice(trace_jsonl, caller_id: str) -> dict:
    """Everything attributable to one agent — the scoped view a responder audits
    after a gate alert, instead of re-reading every agent's activity.

    Returns the caller's outgoing/related observable lines, its cognitive log,
    and a single digest string ready for the semantic auditor.
    """
    observable, cognitive = [], []
    for ev in _events(trace_jsonl):
        b = ev.get("body") or {}
        surface = ev.get("surface")
        if surface == "operational":
            actor = b.get("actor", ev.get("agent_name", "?"))
            target = b.get("target", "?")
            cid = b.get("caller_attested_id")
            if caller_id in (actor, target, cid):
                text = b.get("args_summary") or b.get("result_summary") or ""
                pres = b.get("presented_identity")
                who = f"{actor} -> {target}" + (f" (as {pres!r})" if pres else "")
                observable.append(f"{who}: {text}")
        elif surface == "cognitive":
            if (ev.get("agent_name") or b.get("agent_name")) == caller_id:
                t = b.get("thought") or b.get("plan") or ""
                if t:
                    cognitive.append(t)
    digest = "\n".join(observable)
    return {"caller": caller_id, "observable": observable, "cognitive": cognitive,
            "n_events": len(observable) + len(cognitive), "digest": digest}
