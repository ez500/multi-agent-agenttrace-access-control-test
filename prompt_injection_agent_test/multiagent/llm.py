"""Thin Anthropic Haiku 4.5 client with AgentTrace integration.

Every call:

* loads ``ANTHROPIC_API_KEY`` from ``.env`` (via ``python-dotenv``),
* invokes ``claude-haiku-4-5`` (overridable via ``ANTHROPIC_MODEL``),
* emits an AgentTrace **cognitive** event with prompt/completion summaries and
  real token counts (so the traces.jsonl records a real LLM turn, not a mock),
* emits an AgentTrace **contextual** event describing the outbound HTTPS call
  to ``api.anthropic.com`` (mirrors the paper's "contextual surface" for
  external I/O).

The ``role_label`` is threaded into the cognitive event's ``extraction_method``
field so a reviewer can tell the *attacker* LLM (``role_label="attacker_*"``)
from the *custodian* LLM (``role_label="custodian_*"``) and the *auditor* LLM
(``role_label="injection_auditor"``) apart inside a single trace.

Import is lazy so the demos degrade gracefully with a clear error message
if either the SDK or the API key is missing.
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

    The user message is the untrusted caller input, so it is where injection
    markers live. Summarising ``system + user`` under a single small cap can push
    the user content out entirely once the system prompt grows — which would blind
    the AgentTrace detector's cognitive-surface marker/canary scan. Budgeting the
    two separately keeps the caller's request visible regardless of system length.
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
            field so a reviewer can tell the "attacker LLM" from the "custodian
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


# ---------------------------------------------------------------------------
# Tool-enabled variant: agentic loop with MCP-style tool definitions
# ---------------------------------------------------------------------------

def call_haiku_with_tools(
        system: str,
        user: str,
        *,
        tools: List[Dict[str, Any]],
        tool_dispatcher: Dict[str, Callable[..., str]],
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        role_label: str = "llm_call",
        max_rounds: int = 5,
) -> LLMResponse:
    """Haiku 4.5 completion with Anthropic-native tool use.

    The model may respond with ``tool_use`` content blocks.  When it does, the
    corresponding Python callable is looked up in *tool_dispatcher*, executed,
    and its return value is fed back as a ``tool_result`` message.  The loop
    continues until the model produces a final text response or *max_rounds*
    is exhausted.

    Args:
        system: system prompt.
        user: user message.
        tools: Anthropic tool definitions (list of dicts with ``name``,
            ``description``, ``input_schema``).
        tool_dispatcher: mapping from tool name → Python callable that
            accepts ``**kwargs`` from the model's ``input`` and returns a
            string result.
        model: override the default model name.
        max_tokens: max completion tokens per turn.
        temperature: sampling temperature.
        role_label: tag for AgentTrace cognitive events.
        max_rounds: safety cap on the tool-use loop.
    """
    model_name = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    client = _get_client()

    at = _get_agenttrace()
    logger = at.get_logger() if at is not None else None
    trace_id = at.TraceContext.get_current_trace_id() if at is not None else ""
    span_id = at.TraceContext.new_span_id() if at is not None else ""

    # Contextual surface: outbound external API call.
    if logger is not None:
        logger.record_contextual(
            operation="llm_call",
            source="anthropic.api",
            query_summary=f"model={model_name} role={role_label} tools={[t['name'] for t in tools]}",
            trace_id=trace_id,
            span_id=span_id,
        )

    print(f"\n{'─' * 72}")
    print(f"  ► HAIKU REQUEST (with tools)  role={role_label}  model={model_name}")
    print(f"{'─' * 72}")
    print(f"  [system prompt]\n{_indent(system)}")
    print(f"  [user message]\n{_indent(user)}")
    print(f"  [tools] {[t['name'] for t in tools]}")
    print(f"  [params] max_tokens={max_tokens}  temperature={temperature}")
    print(f"{'─' * 72}")

    messages: List[Dict[str, Any]] = [{"role": "user", "content": user}]
    all_tool_calls: List[ToolCall] = []
    total_p_tok = 0
    total_c_tok = 0

    for round_idx in range(max_rounds):
        resp = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
            tools=tools,
        )

        usage = getattr(resp, "usage", None)
        total_p_tok += int(getattr(usage, "input_tokens", 0) or 0)
        total_c_tok += int(getattr(usage, "output_tokens", 0) or 0)

        # Collect text blocks and tool_use blocks from the response.
        text_parts: List[str] = []
        tool_use_blocks: List[Any] = []
        for block in resp.content:
            btype = getattr(block, "type", "")
            if btype == "text":
                text_parts.append(getattr(block, "text", ""))
            elif btype == "tool_use":
                tool_use_blocks.append(block)

        if text_parts:
            print(f"\n{'─' * 72}")
            print(f"  ◄ HAIKU RESPONSE (round {round_idx})  role={role_label}")
            print(f"{'─' * 72}")
            print(f"  [text]\n{_indent(chr(10).join(text_parts))}")
            print(f"{'─' * 72}")

        if not tool_use_blocks:
            # Model is done — no more tool calls.
            break

        # Build assistant message and tool results for the next turn.
        # The assistant message must include all content blocks as-is.
        assistant_content = []
        for block in resp.content:
            btype = getattr(block, "type", "")
            if btype == "text":
                assistant_content.append({"type": "text", "text": getattr(block, "text", "")})
            elif btype == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for tu_block in tool_use_blocks:
            tool_name = tu_block.name
            tool_input = tu_block.input or {}
            print(f"\n  ◆ TOOL CALL (by LLM): {tool_name}")
            print(f"    input = {json.dumps(tool_input, default=str)}")

            fn = tool_dispatcher.get(tool_name)
            if fn is None:
                result_str = f"[ERROR] Unknown tool: {tool_name}"
            else:
                try:
                    result_str = fn(**tool_input)
                except Exception as exc:
                    result_str = f"[ERROR] {exc!r}"
            print(f"    result = {result_str}")

            all_tool_calls.append(ToolCall(
                tool_name=tool_name,
                tool_input=tool_input,
                result=result_str,
            ))

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu_block.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})
    else:
        print(f"  [WARNING] Tool-use loop hit max_rounds={max_rounds}")

    final_text = "\n".join(text_parts)

    print(f"\n{'─' * 72}")
    print(f"  ◄ HAIKU FINAL  role={role_label}  tool_calls={len(all_tool_calls)}")
    print(f"{'─' * 72}")
    print(f"  [final text]\n{_indent(final_text)}")
    print(f"  [tokens] prompt={total_p_tok}  completion={total_c_tok}  total={total_p_tok + total_c_tok}")
    print(f"{'─' * 72}\n")

    # Cognitive surface: record the full agentic turn.
    if logger is not None:
        tool_summary = "; ".join(
            f"{tc.tool_name}({json.dumps(tc.tool_input, default=str)})→{_summarize(tc.result, 80)}"
            for tc in all_tool_calls
        )
        logger.record_cognitive(
            thought=None,
            model=model_name,
            prompt_summary=_summarize_prompt(system, user),
            completion_summary=_summarize(
                final_text + (" [tools: " + tool_summary + "]" if tool_summary else "")
            ),
            prompt_tokens=total_p_tok,
            completion_tokens=total_c_tok,
            total_tokens=total_p_tok + total_c_tok,
            temperature=temperature,
            trace_id=trace_id,
            span_id=at.TraceContext.new_span_id() if at is not None else "",
            extraction_method=role_label,
        )

    return LLMResponse(
        text=final_text,
        model=model_name,
        prompt_tokens=total_p_tok,
        completion_tokens=total_c_tok,
        tool_calls=all_tool_calls,
    )
