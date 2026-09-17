"""Token and cost accounting, bucketed by role.

The token-efficiency claim needs the DEFENSE's spend separated from the
system's, so `prompts_issued` and `defense_tokens` can be reported against the
number of events the defense actually saw. The deterministic arms (A1/A2) make
no model calls at all, which gives the comparison a zero-cost reference line.

Prices are Claude Haiku 4.5: $1.00 / MTok input, $5.00 / MTok output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

USD_PER_MTOK_IN = 1.00
USD_PER_MTOK_OUT = 5.00

DEFENSE_ROLES = frozenset({"log_processor"})
REPORT_ROLES = frozenset({"md_report"})


@dataclass
class RoleTokens:
    calls: int = 0
    prompt: int = 0
    completion: int = 0
    tool_rounds: int = 0
    retries: int = 0

    def usd(self) -> float:
        return (self.prompt / 1e6) * USD_PER_MTOK_IN + (self.completion / 1e6) * USD_PER_MTOK_OUT


class TokenMeter:
    def __init__(self) -> None:
        self.by_role: Dict[str, RoleTokens] = {}

    def record(self, role: str, prompt: int, completion: int, *,
               tool_rounds: int = 0, retries: int = 0) -> None:
        rt = self.by_role.setdefault(role, RoleTokens())
        rt.calls += 1
        rt.prompt += int(prompt or 0)
        rt.completion += int(completion or 0)
        rt.tool_rounds += int(tool_rounds or 0)
        rt.retries += int(retries or 0)

    def _group(self, roles) -> RoleTokens:
        out = RoleTokens()
        for name, rt in self.by_role.items():
            if name in roles:
                out.calls += rt.calls
                out.prompt += rt.prompt
                out.completion += rt.completion
                out.tool_rounds += rt.tool_rounds
                out.retries += rt.retries
        return out

    @property
    def defense(self) -> RoleTokens:
        return self._group(DEFENSE_ROLES)

    @property
    def report(self) -> RoleTokens:
        return self._group(REPORT_ROLES)

    @property
    def system(self) -> RoleTokens:
        """Everything that is neither the defense nor the post-hoc report."""
        roles = set(self.by_role) - set(DEFENSE_ROLES) - set(REPORT_ROLES)
        return self._group(roles)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        out = {}
        for name, rt in sorted(self.by_role.items()):
            out[name] = {"calls": rt.calls, "prompt_tokens": rt.prompt,
                         "completion_tokens": rt.completion,
                         "tool_rounds": rt.tool_rounds, "retries": rt.retries,
                         "usd": round(rt.usd(), 6)}
        return out
