"""Thin Anthropic Haiku 4.5 client with AgentTrace integration.

Identical in shape to the client used by ``prompt_injection_agent_test`` so all
three demo packages log real LLM turns the same way. Every call:

* loads ``ANTHROPIC_API_KEY`` from ``.env`` (via ``python-dotenv``),
* invokes ``claude-haiku-4-5`` (overridable via ``ANTHROPIC_MODEL``),
* emits an AgentTrace **cognitive** event with prompt/completion summaries and
  real token counts (so the traces.jsonl records a real LLM turn, not a mock),
* emits an AgentTrace **contextual** event describing the outbound HTTPS call
  to ``api.anthropic.com`` (mirrors the paper's "contextual surface" for
  external I/O).

The ``role_label`` is threaded into the cognitive event's ``extraction_method``
field so a reviewer can tell the *orchestrator* LLM (``role_label="orchestrator_*"``)
from the *worker* LLM (``role_label="worker_*"``) and the *auditor* LLM
(``role_label="trajectory_auditor"``) apart inside a single trace.

Import is lazy so the demos degrade gracefully with a clear error message
if either the SDK or the API key is missing — the scripted kill chain still
runs offline, just without the live cognitive turns.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


DEFAULT_MODEL = "claude-haiku-4-5"


@dataclass
class ToolCall:
    """A single tool invocation made by the model."""
    tool_name: str
    tool_input: Dict[str, Any]
    result: str


@dataclass
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    tool_calls: List[ToolCall] = field(default_factory=list)


_client = None
_dotenv_loaded = False


def _ensure_env() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    try:
        from dotenv import load_dotenv
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "python-dotenv is required. Install with `pip install python-dotenv`."
        ) from exc
    # Search parent dirs so the demo scripts can be run from anywhere.
    here = Path(__file__).resolve().parent
    for candidate in (here / ".env", here.parent / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            break
    else:
        load_dotenv()  # fall back to CWD / process env
    _dotenv_loaded = True


def _get_client():
    global _client
    if _client is not None:
        return _client
    _ensure_env()
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The `anthropic` SDK is required. Install with `pip install anthropic`."
        ) from exc
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _get_agenttrace():
    """Return the initialised agenttrace module (or None if unavailable)."""
    try:
        import agenttrace  # type: ignore
    except ImportError:
        return None
    return agenttrace


def _summarize(text: str, cap: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= cap else text[: cap - 1] + "…"


def _summarize_prompt(system: str, user: str,
                      system_cap: int = 120, user_cap: int = 400) -> str:
    """Summarise a system+user prompt, giving the *user* message its own budget.

    The user message is where the interesting, attack-relevant content lives
    (the orchestrator's tasking, a worker's step). Budgeting system and user
    separately keeps that content visible on the cognitive surface regardless of
    how long the system prompt grows, so the trajectory detector's cognitive
    scan is not blinded.
    """
    return (f"[system] {_summarize(system, system_cap)} "
            f"||| [user] {_summarize(user, user_cap)}")


def _indent(text: str, prefix: str = "    ") -> str:
    """Indent every line of *text* for readable verbose output."""
    return "\n".join(prefix + line for line in text.splitlines()) if text else prefix + "(empty)"


def call_haiku(
        system: str,
        user: str,
        *,
        model: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        role_label: str = "llm_call",
) -> LLMResponse:
    """Make one Haiku 4.5 completion and log it to AgentTrace.

    Args:
        system: system prompt.
        user: user message.
        model: override the default model name (else ANTHROPIC_MODEL or Haiku 4.5).
        max_tokens: max completion tokens.
        temperature: sampling temperature (defaults to 0 for reproducibility).
        role_label: short tag used in the cognitive event's ``extraction_method``
            field so a reviewer can tell the "orchestrator LLM" from the "worker
            LLM" and the "auditor LLM" in the same trace.
    """
    model_name = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    client = _get_client()

    at = _get_agenttrace()
    logger = at.get_logger() if at is not None else None
    trace_id = at.TraceContext.get_current_trace_id() if at is not None else ""
    span_id = at.TraceContext.new_span_id() if at is not None else ""

    # ---- Verbose: show the full request being sent to Haiku ---------------
    print(f"\n{'─' * 72}")
    print(f"  ► HAIKU REQUEST  role={role_label}  model={model_name}")
    print(f"{'─' * 72}")
    print(f"  [system prompt]\n{_indent(system)}")
    print(f"  [user message]\n{_indent(user)}")
    print(f"  [params] max_tokens={max_tokens}  temperature={temperature}")
    print(f"{'─' * 72}")

    # Contextual surface: outbound external API call.
    if logger is not None:
        logger.record_contextual(
            operation="llm_call",
            source="anthropic.api",
            query_summary=f"model={model_name} role={role_label}",
            trace_id=trace_id,
            span_id=span_id,
        )

    resp = client.messages.create(
        model=model_name,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    # Anthropic response: list of content blocks; concatenate the text ones.
    text = "".join(
        getattr(block, "text", "") for block in resp.content
        if getattr(block, "type", "") == "text"
    )
    usage = getattr(resp, "usage", None)
    p_tok = int(getattr(usage, "input_tokens", 0) or 0)
    c_tok = int(getattr(usage, "output_tokens", 0) or 0)

    # ---- Verbose: show the full response from Haiku -----------------------
    print(f"\n{'─' * 72}")
    print(f"  ◄ HAIKU RESPONSE  role={role_label}  model={model_name}")
    print(f"{'─' * 72}")
    print(f"  [completion]\n{_indent(text)}")
    print(f"  [tokens] prompt={p_tok}  completion={c_tok}  total={p_tok + c_tok}")
    print(f"{'─' * 72}\n")

    # Cognitive surface: record the LLM turn itself. The auto-extractor in
    # `_maybe_extract_cognitive` will additionally lift any <thinking> tag
    # from the returned text; this event is the "raw call" record.
    if logger is not None:
        logger.record_cognitive(
            thought=None,
            model=model_name,
            prompt_summary=_summarize_prompt(system, user),
            completion_summary=_summarize(text),
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            total_tokens=p_tok + c_tok,
            temperature=temperature,
            trace_id=trace_id,
            span_id=at.TraceContext.new_span_id() if at is not None else "",
            extraction_method=role_label,
        )

    return LLMResponse(
        text=text,
        model=model_name,
        prompt_tokens=p_tok,
        completion_tokens=c_tok,
        tool_calls=[],
    )
