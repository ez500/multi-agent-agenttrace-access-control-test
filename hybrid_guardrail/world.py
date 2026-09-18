"""The guarded world: one secret, read only through the parameterized hard gate."""

from __future__ import annotations

from credential import Authz, GateDecision, resource_gate

SECRET_CANARY = "VAULT-ROOT-KEY-9C2F-D3E7"


def read_resource(mode: str, *, caller_attested_id: str, presented_token: str,
                  authz: Authz):
    """Attempt the guarded read. Returns (returned_value, GateDecision).

    The secret escapes only when the gate allows; otherwise a denial string is
    returned (the canary never appears in it)."""
    decision = resource_gate(mode, caller_attested_id=caller_attested_id,
                             presented_token=presented_token, authz=authz)
    if decision.allow:
        return SECRET_CANARY, decision
    return f"[ACCESS DENIED] {decision.reason}", decision
