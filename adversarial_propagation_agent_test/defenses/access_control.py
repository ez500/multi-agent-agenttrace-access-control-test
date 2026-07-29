"""Branch A: Adaptive deterministic access control.

Implements the paper's Table XIV thresholds as a stateless, in-process firewall
that intercepts tool calls before they reach the execution layer:

    taint > 0.8   -> IMMEDIATE_QUARANTINE   (block sensitive tools)
    0.5 < t<=0.8  -> RESTRICTED_OPERATION   (block writes, allow reads)
    t <= 0.5      -> LOG_SUSPICIOUS_ACTIVITY (allow, warn)

This is the "active firewall" described in the task brief. It does not need to
read AgentTrace logs to make its decision -- it just does math on the taint
value that propagated with the message. AgentTrace still logs the *attempted*
call and the [BLOCKED] outcome (that is Branch A's "flight recorder" role).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class AccessDecision:
    allow: bool
    action: str        # "IMMEDIATE_QUARANTINE" | "RESTRICTED_OPERATION" | "LOG_SUSPICIOUS_ACTIVITY" | "ALLOW"
    reason: str


class DeterministicAccessControl:
    """Stateless taint-threshold firewall (T-Guard Access Control Manager)."""

    HIGH_THRESHOLD: float = 0.8
    MEDIUM_THRESHOLD: float = 0.5

    @classmethod
    def evaluate(
            cls,
            agent_taint: float,
            tool_name: str,
            sensitive_tools: FrozenSet[str] = frozenset({"wipe_database", "quarantine_network"}),
    ) -> AccessDecision:
        is_sensitive = tool_name in sensitive_tools

        if agent_taint > cls.HIGH_THRESHOLD and is_sensitive:
            return AccessDecision(
                allow=False,
                action="IMMEDIATE_QUARANTINE",
                reason=(
                    f"Taint score {agent_taint:.2f} > {cls.HIGH_THRESHOLD} "
                    f"and '{tool_name}' is sensitive."
                ),
            )
        if cls.MEDIUM_THRESHOLD < agent_taint <= cls.HIGH_THRESHOLD and is_sensitive:
            return AccessDecision(
                allow=False,
                action="RESTRICTED_OPERATION",
                reason=(
                    f"Taint score {agent_taint:.2f} in restricted band; "
                    f"'{tool_name}' write blocked."
                ),
            )
        if agent_taint <= cls.MEDIUM_THRESHOLD:
            return AccessDecision(
                allow=True,
                action="LOG_SUSPICIOUS_ACTIVITY",
                reason=f"Taint score {agent_taint:.2f} within tolerance.",
            )
        # Non-sensitive tool in a tainted band: allow but log.
        return AccessDecision(
            allow=True,
            action="LOG_SUSPICIOUS_ACTIVITY",
            reason=f"Tool '{tool_name}' not in sensitive set; taint {agent_taint:.2f}.",
        )
