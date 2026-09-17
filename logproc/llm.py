"""Claude Haiku 4.5 turns, instrumented and metered.

Ported from archive/prompt_injection_agent_test/multiagent/llm.py with three
changes:

  * `text_parts` is initialised BEFORE the round loop. In the original it was
    scoped inside, so max_rounds<=0 raised UnboundLocalError and a final round
    emitting only tool_use left the variable unbound (archive bug A1).
  * the noisy per-turn printing is gone -- 180 runs at concurrency 4 would
    interleave into unreadable mush.
  * every call reports usage into a TokenMeter under a role label, which is
    what separates defense spend from system spend in the results.

The .env is found by walking up from this file, not by the original's brittle
two-level search.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DEFAULT_MODEL = "claude-haiku-4-5"

_CLIENT = None
_CLIENT_LOCK = threading.Lock()
_ENV_LOADED = False


def _ensure_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        _ENV_LOADED = True
        return
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        cand = parent / ".env"
        if cand.exists():
            load_dotenv(cand)
            break
    _ENV_LOADED = True


def _get_client():
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _ensure_env()
            import anthropic
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Copy .env.example to .env "
                    "in the scenario directory and fill it in."
                )
            # Generous retries: at concurrency 4 each run has two in-flight
            # request sources, so 429s are expected rather than exceptional.
            _CLIENT = anthropic.Anthropic(api_key=key, max_retries=5)
        return _CLIENT


def _get_agenttrace():
    try:
        import agenttrace
        return agenttrace
    except ImportError:
        return None


@dataclass
class ToolCall:
    name: str
    input: Dict[str, Any]
    result: str = ""


@dataclass
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: List[ToolCall] = field(default_factory=list)
    rounds: int = 0


def _record_surfaces(role_label: str, model_name: str, system: str, user: str,
                     text: str, p_tok: int, c_tok: int, temperature: float,
                     tools: Optional[List[Dict[str, Any]]] = None,
                     emitter: Optional[str] = None) -> None:
    at = _get_agenttrace()
    if at is None:
        return
    logger = at.get_logger()
    if logger is None:
        return
    trace_id = at.TraceContext.get_current_trace_id()
    span_id = at.TraceContext.new_span_id()
    extra = {"emitter": emitter} if emitter else {}
    tool_names = [t["name"] for t in (tools or [])]
    logger.record_contextual(
        operation="llm_call", source="anthropic.api",
        query_summary=f"model={model_name} role={role_label} tools={tool_names}",
        trace_id=trace_id, span_id=span_id, **extra)
    logger.record_cognitive(
        model=model_name,
        prompt_summary=system[:400],
        completion_summary=text[:400],
        prompt_tokens=p_tok, completion_tokens=c_tok,
        total_tokens=p_tok + c_tok, temperature=temperature,
        extraction_method=role_label,
        trace_id=trace_id, span_id=span_id, **extra)


def call_haiku(system: str, user: str, *, model: Optional[str] = None,
               max_tokens: int = 700, temperature: float = 0.0,
               role_label: str = "llm_call", meter: Any = None,
               emitter: Optional[str] = None) -> LLMResponse:
    """A single Haiku turn with no tools."""
    model_name = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    client = _get_client()
    resp = client.messages.create(
        model=model_name, max_tokens=max_tokens, temperature=temperature,
        system=system, messages=[{"role": "user", "content": user}],
    )
    usage = getattr(resp, "usage", None)
    p_tok = int(getattr(usage, "input_tokens", 0) or 0)
    c_tok = int(getattr(usage, "output_tokens", 0) or 0)
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    if meter is not None:
        meter.record(role_label, p_tok, c_tok)
    _record_surfaces(role_label, model_name, system, user, text,
                     p_tok, c_tok, temperature, emitter=emitter)
    return LLMResponse(text=text, model=model_name,
                       prompt_tokens=p_tok, completion_tokens=c_tok, rounds=1)


def call_haiku_with_tools(
    system: str, user: str, *,
    tools: List[Dict[str, Any]],
    tool_dispatcher: Dict[str, Callable[..., str]],
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    role_label: str = "llm_call",
    max_rounds: int = 4,
    meter: Any = None,
    emitter: Optional[str] = None,
) -> LLMResponse:
    """Haiku turn with Anthropic-native tool use, looping until final text."""
    model_name = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    client = _get_client()

    messages: List[Dict[str, Any]] = [{"role": "user", "content": user}]
    all_tool_calls: List[ToolCall] = []
    text_parts: List[str] = []          # A1 fix: bound before the loop
    total_p = total_c = 0
    rounds = 0

    for _ in range(max(0, max_rounds)):
        rounds += 1
        resp = client.messages.create(
            model=model_name, max_tokens=max_tokens, temperature=temperature,
            system=system, messages=messages, tools=tools,
        )
        usage = getattr(resp, "usage", None)
        total_p += int(getattr(usage, "input_tokens", 0) or 0)
        total_c += int(getattr(usage, "output_tokens", 0) or 0)

        tool_uses = []
        for block in resp.content:
            btype = getattr(block, "type", "")
            if btype == "text":
                text_parts.append(getattr(block, "text", ""))
            elif btype == "tool_use":
                tool_uses.append(block)

        if not tool_uses:
            break

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for tu in tool_uses:
            fn = tool_dispatcher.get(tu.name)
            # tool_use.input is already a dict from the SDK; never string-match it.
            kwargs = dict(tu.input or {})
            if fn is None:
                out = f"ERROR: no such tool {tu.name!r}"
            else:
                try:
                    out = str(fn(**kwargs))
                except Exception as exc:
                    out = f"ERROR: {type(exc).__name__}: {exc}"
            all_tool_calls.append(ToolCall(name=tu.name, input=kwargs, result=out))
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out})
        messages.append({"role": "user", "content": results})

    text = "\n".join(t for t in text_parts if t)
    if meter is not None:
        meter.record(role_label, total_p, total_c, tool_rounds=rounds)
    _record_surfaces(role_label, model_name, system, user, text,
                     total_p, total_c, temperature, tools=tools, emitter=emitter)
    return LLMResponse(text=text, model=model_name, prompt_tokens=total_p,
                       completion_tokens=total_c, tool_calls=all_tool_calls,
                       rounds=rounds)
