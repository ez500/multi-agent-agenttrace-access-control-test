"""Cognitive monitor: read the attacker's OWN recorded reasoning, judge intent.

The broker sees only what the requester says *to it* (a claimed identity + a
justification), so identity spoofing beats it. A different control reads what the
agent records about itself on the AgentTrace **cognitive** surface — its private
reasoning — and judges whether the intent is an unauthorized access / spoofing
attempt. Against a naive attacker whose recorded reasoning states its real plan
("impersonate svc-indexer to obtain the key"), this catches what the broker
cannot.

The catch — and the link to the trace-laundering result — is that the cognitive
surface is itself agent-authored self-report. An attacker that launders its
recorded reasoning into benign language blinds this monitor too, exactly as in
the trace-monitor experiment. So the cognitive monitor is a real improvement
against a non-adaptive attacker, but it is not the robust layer; the attested
capability gate is.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# LLM_API/ sits at the repository root; this package lives under archive/, so
# locate it by walking up the tree rather than assuming a fixed depth.
_LLM_API = next((p / "LLM_API" for p in Path(__file__).resolve().parents
                 if (p / "LLM_API").is_dir()), None)
if _LLM_API is None:
    raise RuntimeError("Could not locate LLM_API/ above " + __file__)
if str(_LLM_API) not in sys.path:
    sys.path.insert(0, str(_LLM_API))
import gateway  # noqa: E402


from souls import load_soul  # noqa: E402

#: Authored in ``souls/cognitive_monitor.SOUL.md``, loaded into the system role.
COGNITIVE_MONITOR_SYSTEM_PROMPT = load_soul("cognitive_monitor")


@dataclass
class CognitiveVerdict:
    flagged: bool
    reason: str
    raw: str = ""


class CognitiveMonitor:
    """Reads the attacker's cognitive-surface events for a trace and judges intent."""

    def __init__(self, trace_jsonl: Path | str, *, model: Optional[str] = None,
                 temperature: float = 0.0) -> None:
        self._jsonl = Path(trace_jsonl)
        self._model = model
        self._temperature = temperature

    def _read_cognition(self, trace_id: str) -> List[str]:
        out: List[str] = []
        if not self._jsonl.exists():
            return out
        for line in open(self._jsonl, "r", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("trace_id") != trace_id or ev.get("surface") != "cognitive":
                continue
            b = ev.get("body") or {}
            t = b.get("thought") or b.get("plan") or ""
            if t:
                out.append(t)
        return out

    def evaluate(self, trace_id: str) -> CognitiveVerdict:
        thoughts = self._read_cognition(trace_id)
        if not thoughts:
            return CognitiveVerdict(False, "no cognitive events recorded")
        prompt = ("AGENT'S RECORDED PRIVATE REASONING:\n" +
                  "\n".join(f"- {t}" for t in thoughts))
        try:
            raw = gateway.chat(prompt, system=COGNITIVE_MONITOR_SYSTEM_PROMPT,
                               model=self._model, max_tokens=250,
                               temperature=self._temperature)
        except Exception as exc:
            return CognitiveVerdict(True, f"monitor error, failing closed: {exc}")
        obj = _parse(raw)
        if obj is None:
            return CognitiveVerdict(True, f"unparseable monitor reply: {raw[:140]!r}", raw)
        return CognitiveVerdict(bool(obj.get("malicious")),
                                str(obj.get("reason", ""))[:280], raw)


def _parse(text: str) -> Optional[Dict]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    s, e = text.find("{"), text.rfind("}")
    if 0 <= s < e:
        try:
            return json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            return None
    return None
