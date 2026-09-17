"""Deterministic incident reconstruction from the recorded logs.

Template-first on purpose. A reviewer may treat INCIDENT.md as evidence, so the
authoritative sections are computed directly from traces.jsonl, verdicts.jsonl
and result.json -- never narrated by a model that could hallucinate a timeline.
An optional `--md-llm` narrative is appended, clearly labelled, and its tokens
are bucketed separately (role md_report) and excluded from defense_tokens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _fmt_event_row(ev: Dict[str, Any]) -> str:
    body = ev.get("body") or {}
    surface = ev.get("surface", "")
    agent = ev.get("agent_name", "")
    if surface == "operational":
        rendering = f"{body.get('method','')} [{body.get('status','')}]"
        if body.get("result_summary"):
            rendering += f" -> {body['result_summary'][:80]}"
    elif surface == "contextual":
        rendering = f"{body.get('operation','')} <{body.get('source','')}>"
        summ = body.get("response_summary") or body.get("query_summary") or ""
        if summ:
            rendering += f": {summ[:80]}"
    elif surface == "cognitive":
        summ = body.get("thought") or body.get("completion_summary") or ""
        rendering = f"(reasoning) {summ[:90]}"
    else:
        rendering = surface
    return f"| {agent} | {surface} | {rendering} |"


def render_incident_md(run_dir: Path) -> str:
    run_dir = Path(run_dir)
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    events = _load_jsonl(run_dir / "traces.jsonl")
    verdicts = _load_jsonl(run_dir / "verdicts.jsonl")

    outcome = result["outcome"].upper()
    fail = result.get("failure", {})
    neut = result.get("neutralize", {})

    L: List[str] = []
    L.append(f"# Incident reconstruction — {result['run_id']}")
    L.append("")
    L.append(f"**Scenario:** {result['scenario']}  ")
    L.append(f"**Arm:** {result['arm']} ({result.get('arm_label','')})  ")
    L.append(f"**Trigger:** {result['trigger']}  ")
    L.append(f"**Outcome:** `{outcome}`")
    L.append("")

    # Decision point as literal arithmetic.
    L.append("## Decision point")
    fseq = fail.get("seq")
    nseq = neut.get("seq")
    if fseq is None and nseq is None:
        L.append("No failure occurred and no neutralize was issued — `no_incident`.")
    elif fseq is None:
        L.append(f"No failure occurred. Neutralize fired at seq {nseq} — `resolved`.")
    elif nseq is None:
        L.append(f"Failure at seq {fseq}. No neutralize was ever issued — `evaded`.")
    else:
        rel = "<" if fseq < nseq else ">="
        verdict = "EVADED" if fseq < nseq else "RESOLVED"
        L.append(f"`failure_seq({fseq}) {rel} neutralize_seq({nseq})` ⇒ **{verdict}**")
    L.append("")

    # Full timeline.
    L.append("## Timeline")
    L.append("")
    L.append("| agent | surface | event |")
    L.append("|---|---|---|")
    for ev in events:
        L.append(_fmt_event_row(ev))
    L.append("")

    # Trigger log -- the per-run token-efficiency evidence.
    L.append("## Trigger log")
    L.append("")
    L.append("| batch | queue | events | elided | verdict | conf | p_tok | c_tok | ms |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for v in verdicts:
        L.append("| {batch_index} | {queue_depth_at_issue} | {events_considered} | "
                 "{events_elided} | {verdict} | {confidence} | {prompt_tokens} | "
                 "{completion_tokens} | {latency_ms:.0f} |".format(**{**v, "latency_ms": float(v.get("latency_ms",0))}))
    L.append("")

    # Evidence the processor held at the moment of failure.
    if fseq is not None and verdicts:
        pre = [v for v in verdicts if v.get("batch_index", 0) and v.get("neutralize_seq") is None]
        L.append("## Evidence held before failure")
        L.append("")
        last_before = None
        for v in verdicts:
            ns = v.get("neutralize_seq")
            if ns is None or ns >= fseq:
                last_before = v
        if last_before is not None:
            L.append(f"Last verdict before the failure event (seq {fseq}): "
                     f"**{last_before.get('verdict')}** — {last_before.get('reason','')}")
        else:
            L.append("The processor had not yet issued a verdict when the failure occurred.")
        L.append("")

    # Token ledger.
    cost = result.get("cost_usd", {})
    proc = result.get("processor", {})
    L.append("## Token ledger")
    L.append("")
    L.append(f"- prompts issued by the defense: **{proc.get('prompts_issued', 0)}**")
    L.append(f"- defense tokens: {proc.get('prompt_tokens',0)} in / {proc.get('completion_tokens',0)} out")
    L.append(f"- defense cost: ${cost.get('defense', 0):.5f}  ·  system cost: ${cost.get('system', 0):.5f}")
    L.append(f"- events the defense saw: {result.get('events_admitted', 0)}  ·  "
             f"processor-authored events filtered: {result.get('events_filtered_processor_authored', 0)}")
    L.append("")

    return "\n".join(L)


def narrate_llm(sections: str, souls_dir: str, meter: Any = None,
                model: Optional[str] = None) -> str:
    """Optional model narrative. Strictly post-episode; cannot affect outcomes."""
    from . import llm
    from .souls import load_soul
    system = load_soul(souls_dir, "incident_writer")
    resp = llm.call_haiku(system, sections[:6000], model=model, role_label="md_report",
                      temperature=0.0, max_tokens=500, meter=meter)
    return ("\n## Narrative\n\n"
            "> Generated prose. The authoritative record is the timeline above.\n\n"
            + resp.text)
