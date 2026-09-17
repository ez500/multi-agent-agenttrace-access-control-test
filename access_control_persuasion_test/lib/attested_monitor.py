"""Monitor over the OPERATIONAL surface's harness-attested fields.

NOTE: this is NOT a fourth AgentTrace surface. AgentTrace has three surfaces —
operational / cognitive / contextual. This monitor reads the *operational* surface,
but only the fields the harness emits and the agent cannot forge (``emitter ==
"harness"``: the attested caller id and the identity presented). The conversation
monitor reads the SAME operational events but trusts a different provenance — the
agent-authored message text. "Attested" here names a provenance level within the
operational surface, not a surface of its own.

Because the attested caller id is harness-emitted, this monitor's signal does not
depend on the agent's cooperation.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

_LLM_API = Path(__file__).resolve().parent.parent.parent / "LLM_API"
if str(_LLM_API) not in sys.path:
    sys.path.insert(0, str(_LLM_API))
import gateway  # noqa: E402

from souls import load_soul  # noqa: E402
from monitors import _parse  # reuse the tolerant JSON parser  # noqa: E402

ATTESTED_MONITOR_SYSTEM_PROMPT = load_soul("attested_monitor")


@dataclass
class AttestedVerdict:
    flagged: bool
    reason: str
    raw: str = ""


class AttestedMonitor:
    def __init__(self, *, model: Optional[str] = None, temperature: float = 0.0) -> None:
        self._model = model
        self._temperature = temperature

    def evaluate_trace(self, trace_jsonl) -> AttestedVerdict:
        """Read the harness-attested action records off an AgentTrace (operational
        surface, emitter=harness, attested caller id) and judge them."""
        from trace_surfaces import read_attested
        return self.evaluate(read_attested(trace_jsonl))

    def evaluate(self, action_log: List[str]) -> AttestedVerdict:
        """`action_log` is an ordered list of attested action descriptions."""
        if not action_log:
            return AttestedVerdict(False, "no attested actions recorded")
        prompt = ("FRAMEWORK-ATTESTED ACTION RECORD, IN ORDER:\n" +
                  "\n".join(f"- {a}" for a in action_log))
        try:
            raw = gateway.chat(prompt, system=ATTESTED_MONITOR_SYSTEM_PROMPT,
                               model=self._model, max_tokens=250,
                               temperature=self._temperature)
        except Exception as exc:
            return AttestedVerdict(True, f"monitor error, failing closed: {exc}")
        obj = _parse(raw)
        if obj is None:
            return AttestedVerdict(True, f"unparseable monitor reply: {raw[:140]!r}", raw)
        return AttestedVerdict(bool(obj.get("malicious")),
                               str(obj.get("reason", ""))[:280], raw)
