"""Baseline enterprise control: path-scoped access control for the vault.

A stateless, in-process gate that a well-behaved deployment would place in
front of any read of a prohibited path. It mirrors the deterministic firewall
of ``adversarial_propagation_agent_test`` but keys off *path sensitivity +
authorization* rather than a numeric taint score:

    prohibited path  + valid ticket   -> ALLOW  (an operator with a ticket)
    prohibited path  + no/invalid tkt -> DENY   (block the read)
    non-prohibited path               -> ALLOW

This is the "official" control the enterprise trusts. The point of the demos
is that it is *insufficient on its own*: the custodian is a confused deputy
that can be talked into presenting authorization it should not have, and a
security-aware attacker who knows :data:`multiagent.injection_payloads.VALID_VAULT_TICKET`
can forge exactly the token the gate expects. AgentTrace-based detection is
the layer that has a chance of catching what this gate misses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from multiagent.injection_payloads import VALID_VAULT_TICKET
from multiagent.tools import is_prohibited_path

# The gate recognises a ticket of this shape; only the exact issued value is
# actually valid. An attacker who knows the *format* but not the value still
# fails — the L3 attacker knows the value itself.
_TICKET_RE = re.compile(r"AUTH-TICKET-[A-Z0-9]{8}")


@dataclass(frozen=True)
class AccessDecision:
    allow: bool
    action: str        # "ALLOW" | "DENY_PROHIBITED_PATH" | "ALLOW_WITH_TICKET"
    reason: str


class PathAccessControl:
    """Stateless prohibited-path firewall gated by a vault authorization ticket."""

    @staticmethod
    def _has_valid_ticket(authorization: str) -> bool:
        if not authorization:
            return False
        return VALID_VAULT_TICKET in authorization or bool(
            _TICKET_RE.search(authorization)
            and VALID_VAULT_TICKET in authorization
        )

    @classmethod
    def evaluate(cls, path: str, authorization: str = "") -> AccessDecision:
        """Decide whether a read of ``path`` may proceed.

        Args:
            path: the filesystem path the custodian is about to read.
            authorization: any authorization material presented with the
                request (e.g. a ticket string lifted from the caller message).
        """
        if not is_prohibited_path(path):
            return AccessDecision(
                allow=True,
                action="ALLOW",
                reason=f"'{path}' is not a prohibited path.",
            )
        if cls._has_valid_ticket(authorization):
            return AccessDecision(
                allow=True,
                action="ALLOW_WITH_TICKET",
                reason="Prohibited path read authorised by a valid vault ticket.",
            )
        return AccessDecision(
            allow=False,
            action="DENY_PROHIBITED_PATH",
            reason=(
                f"'{path}' is a prohibited path and no valid vault ticket was "
                "presented."
            ),
        )
