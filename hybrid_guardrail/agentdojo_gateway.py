"""Run AgentDojo's tool-calling agent through the APIM/MSAL gateway.

AgentDojo's agents normally use a provider client (OpenAI/Anthropic direct). We
only have the APIM-fronted gateway (`gateway.chat`, no native tool-calling API),
so we subclass AgentDojo's PROMPTING protocol (`PromptingLLM`), which drives tools
via a text protocol (`<function-call>...</function-call>`) it parses itself. We
reuse its `_make_tools_prompt` / `_parse_model_output` and only replace the model
call with `gateway.chat`.

Verified: workspace/user_task_0 solves (utility=True) end-to-end via the gateway,
so a full AgentDojo benchmark can run on our infrastructure. Build the runtime
monitor as a separate BasePipelineElement inserted into the pipeline.

    from agentdojo_gateway import GatewayLLM, build_pipeline
    pipe = build_pipeline()               # optionally pass extra elements
"""
from __future__ import annotations

from _bootstrap import REPO_ROOT  # noqa: F401  (ensures LLM_API on path)
import gateway

from agentdojo.agent_pipeline import (PromptingLLM, AgentPipeline, SystemMessage,
                                      InitQuery, ToolsExecutionLoop, ToolsExecutor)
from agentdojo.agent_pipeline.llms.prompting_llm import (get_text_content_as_str,
                                                         text_content_block_from_string)
from agentdojo.functions_runtime import EmptyEnv
from agentdojo.types import ChatAssistantMessage

DEFAULT_SYSTEM = "You are an AI assistant that helps a user by calling tools when needed."


class _Msg:
    """Minimal stand-in for an OpenAI completion message (only `.content` is read)."""
    def __init__(self, content: str):
        self.content = content


class GatewayLLM(PromptingLLM):
    """PromptingLLM whose completions come from `gateway.chat`."""

    def __init__(self, model: str = "gateway", temperature: float = 0.0,
                 max_tokens: int = 1024):
        self.client = None
        self.model = model
        self.temperature = temperature
        self.reasoning_effort = None
        self._max_tokens = max_tokens

    def _complete(self, prompt: str, system: str | None) -> str:
        return gateway.chat(prompt, system=system, temperature=self.temperature or 0.0,
                            max_tokens=self._max_tokens)

    def query(self, query, runtime, env=EmptyEnv(), messages=(), extra_args=None):
        extra_args = {} if extra_args is None else extra_args
        messages = list(messages)
        adapted = [self._tool_message_to_user_message(m) if m["role"] == "tool" else m
                   for m in messages]
        sysmsg, _ = self._get_system_message(messages)
        sysmsg = self._make_tools_prompt(sysmsg, list(runtime.functions.values()))
        sys_text = get_text_content_as_str(sysmsg["content"] or []) if sysmsg else None
        convo = [f'{m["role"].upper()}: {get_text_content_as_str(m.get("content") or [])}'
                 for m in adapted if m["role"] != "system"]
        prompt = "\n\n".join(convo) or query

        raw = self._complete(prompt, sys_text)
        if len(runtime.functions) == 0 or "<function-call>" not in raw:
            out = ChatAssistantMessage(role="assistant",
                                       content=[text_content_block_from_string(raw)], tool_calls=[])
            return query, runtime, env, [*messages, out], extra_args

        out = None
        for _ in range(self._MAX_ATTEMPTS):
            try:
                out = self._parse_model_output(_Msg(raw))
                break
            except Exception as e:  # invalid tool-call formatting -> nudge and retry
                raw = self._complete(prompt + f"\n\nInvalid function calling output: {e}", sys_text)
        if out is None:
            out = ChatAssistantMessage(role="assistant",
                                       content=[text_content_block_from_string(raw)], tool_calls=[])
        return query, runtime, env, [*messages, out], extra_args


def build_pipeline(*, system: str = DEFAULT_SYSTEM, extra_elements=(),
                   max_iters: int = 8, name: str = "gateway-prompting") -> AgentPipeline:
    """Standard AgentDojo tool-calling pipeline driven by the gateway.

    `extra_elements` are inserted after InitQuery (e.g. a runtime monitor element).
    """
    llm = GatewayLLM()
    elements = [SystemMessage(system), InitQuery(), *extra_elements, llm,
                ToolsExecutionLoop([ToolsExecutor(), llm], max_iters=max_iters)]
    pipe = AgentPipeline(elements)
    pipe.name = name
    return pipe
