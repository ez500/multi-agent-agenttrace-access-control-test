"""Conversation monitor: judge the OBSERVABLE external dialogue on the wire.

Between the cognitive monitor (reads self-reported reasoning — fully agent-authored,
so a black-box attacker gives it nothing) and the attested monitor (reads
harness-logged action metadata + the ground-truth identity), there is a realistic
middle surface: the actual inter-agent messages that crossed the wire. The agent
authors its own messages (it can phrase them innocuously), but it does NOT author
the peer's replies, nor can it hide that a message was sent. This monitor reads that
observable dialogue only — no private reasoning, no attested identity — and judges
the pattern of the exchange.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_LLM_API = Path(__file__).resolve().parent.parent.parent / "LLM_API"
if str(_LLM_API) not in sys.path:
    sys.path.insert(0, str(_LLM_API))
import gateway  # noqa: E402

from souls import load_soul  # noqa: E402
from monitors import _parse  # reuse tolerant JSON parser  # noqa: E402

CONVERSATION_MONITOR_SYSTEM_PROMPT = load_soul("conversation_monitor")


@dataclass
class ConversationVerdict:
    flagged: bool
    reason: str
    raw: str = ""


class ConversationMonitor:
    def __init__(self, *, model: Optional[str] = None, temperature: float = 0.0) -> None:
        self._model = model
        self._temperature = temperature

    def evaluate_trace(self, trace_jsonl) -> ConversationVerdict:
        """Read the observable dialogue off an AgentTrace (operational surface,
        excluding the attested caller id) and judge it."""
        from trace_surfaces import read_observable
        return self.evaluate(read_observable(trace_jsonl))

    def evaluate(self, transcript: List[str]) -> ConversationVerdict:
        """`transcript` is the observable dialogue, one line per utterance."""
        if not transcript:
            return ConversationVerdict(False, "no conversation observed")
        prompt = ("OBSERVED CONVERSATION (messages on the wire, in order):\n" +
                  "\n".join(transcript))
        try:
            raw = gateway.chat(prompt, system=CONVERSATION_MONITOR_SYSTEM_PROMPT,
                               model=self._model, max_tokens=250,
                               temperature=self._temperature)
        except Exception as exc:
            return ConversationVerdict(True, f"monitor error, failing closed: {exc}")
        obj = _parse(raw)
        if obj is None:
            return ConversationVerdict(True, f"unparseable monitor reply: {raw[:140]!r}", raw)
        return ConversationVerdict(bool(obj.get("malicious")),
                                   str(obj.get("reason", ""))[:280], raw)
