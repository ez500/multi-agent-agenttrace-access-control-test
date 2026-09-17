"""AgentTrace three-surface JSONL -> Invariant Guardrails trace format.

FAIRNESS-CRITICAL. This mapping decides what the deterministic control arms can
see, so it is isolated here, unit-tested against golden fixtures, and described
explicitly in the paper. Both the control and the semantic processor are handed
the SAME PendingEvent batches at the SAME trigger points; only the encoding
differs. If this adapter dropped information the semantic arm receives, the
comparison would be rigged in the semantic arm's favour.

Invariant consumes an OpenAI-shaped message list:
    {"role": "user"|"assistant"|"tool", "content": str,
     "tool_calls": [{"id","type","function":{"name","arguments"}}]}

Mapping:
    operational  status=start     -> assistant message carrying a tool_call
                 status=complete  -> tool message (the ToolOutput) for that call
                 status=error     -> tool message with the error text
    contextual                    -> tool message; external/untrusted sources are
                                     prefixed with an explicit untrusted marker so
                                     a dataflow rule can key on provenance
    cognitive                     -> assistant message (agent-authored self-report)

Every emitted message keeps the originating agent name and surface so policies
can reason about who acted, and the untrusted marker is harness-controlled --
an agent cannot clear it by writing a different string.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

# Sources whose content originated outside the trust boundary.
UNTRUSTED_SOURCES = {"external", "web", "unknown", "attacker", "public_intake"}
UNTRUSTED_MARKER = "[EXTERNAL_UNTRUSTED]"


def _args_of(body: Dict[str, Any]) -> Dict[str, Any]:
    """Arguments for a synthetic tool call.

    Load-bearing fields recorded as explicit **extra kwargs (command, target,
    tool) are passed through verbatim. This matters: AgentTrace's auto-wrapper
    caps args_summary at 80 chars, so a rule matching on a long destructive
    command would randomly miss if it read args_summary instead.
    """
    args: Dict[str, Any] = {}
    for k in ("command", "target", "tool", "who", "url", "path", "args_summary"):
        if body.get(k) not in (None, ""):
            args[k] = body[k]
    return args


def to_invariant_trace(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw AgentTrace event dicts into an Invariant message list."""
    msgs: List[Dict[str, Any]] = []
    call_ids: Dict[str, str] = {}
    counter = 0

    for ev in events:
        surface = ev.get("surface", "")
        agent = ev.get("agent_name", "")
        body = ev.get("body") or {}

        if surface == "operational":
            method = body.get("method", "")
            status = body.get("status", "")
            key = f"{agent}:{method}:{ev.get('span_id','')}"

            if status == "start":
                counter += 1
                cid = str(counter)
                call_ids[key] = cid
                msgs.append({
                    "role": "assistant",
                    "content": "",
                    "agent": agent,
                    "surface": surface,
                    "tool_calls": [{
                        "id": cid,
                        "type": "function",
                        "function": {"name": method, "arguments": _args_of(body)},
                    }],
                })
            else:
                cid = call_ids.get(key)
                if cid is None:
                    counter += 1
                    cid = str(counter)
                content = body.get("result_summary") or ev.get("error") or body.get("error") or ""
                if status == "error":
                    content = f"ERROR: {content}"
                msgs.append({
                    "role": "tool", "tool_call_id": cid,
                    "content": str(content), "agent": agent, "surface": surface,
                })

        elif surface == "contextual":
            counter += 1
            cid = str(counter)
            op = body.get("operation", "")
            src = body.get("source", "")
            content = str(
                body.get("response_summary") or body.get("query_summary") or ""
            )
            if src in UNTRUSTED_SOURCES:
                content = f"{UNTRUSTED_MARKER} {content}"
            # The call that produced this output, so dataflow rules have a pair.
            msgs.append({
                "role": "assistant", "content": "", "agent": agent, "surface": surface,
                "tool_calls": [{
                    "id": cid, "type": "function",
                    "function": {"name": op or "io", "arguments": {"source": src}},
                }],
            })
            msgs.append({
                "role": "tool", "tool_call_id": cid, "content": content,
                "agent": agent, "surface": surface,
            })

        elif surface == "cognitive":
            text = " ".join(
                str(body[k]) for k in
                ("thought", "plan", "reflection", "completion_summary", "prompt_summary")
                if body.get(k)
            )
            if text:
                msgs.append({
                    "role": "assistant", "content": text,
                    "agent": agent, "surface": surface,
                })

    return msgs
