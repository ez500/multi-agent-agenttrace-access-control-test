"""Defenses that live inside the ExploitGym harness, over its own agents.

The post-mortem's operator-side recommendation (§V, §VI): instrument within the
harness, correlate across agents, and respond at machine speed. Three modules:

* :mod:`defenses.fleet_policy` — Layer 1, a deterministic policy over the
  *aggregate* sealed fleet trace. Its result is that every agent is individually
  sub-threshold while the union crosses policy (the headline).
* :mod:`defenses.semantic_deferral` — Layer 2, a Claude Haiku 4.5 agent reading
  a live byte-cursor tail of the sealed feed, catching the residual case the
  rules do not enumerate.
* :mod:`defenses.response` — the :class:`~defenses.response.FleetGovernor` and
  the graded, no-human-in-the-loop response ladder
  ``OBSERVE -> RESTRICT_TOOL -> REVOKE_CREDENTIAL -> HALT_AGENT -> HALT_FLEET``.
"""

from .fleet_policy import (
    CREDENTIAL_PROVENANCE,
    FLEET_POLICY,
    FLEET_SIGNALS,
    PER_AGENT_ALERT,
    AgentScore,
    FleetPolicyEnforcer,
    FleetVerdict,
    Signal,
)
from .response import (
    HALT_AGENT,
    HALT_FLEET,
    LADDER,
    OBSERVE,
    REVOKE_CREDENTIAL,
    RESTRICT_TOOL,
    FleetGovernor,
    GovernorSummary,
    ResponseAction,
)
from .semantic_deferral import (
    DeferralDecision,
    SemanticDeferralAgent,
    haiku_fleet_auditor,
)

__all__ = [
    # fleet_policy
    "CREDENTIAL_PROVENANCE",
    "FLEET_POLICY",
    "FLEET_SIGNALS",
    "PER_AGENT_ALERT",
    "AgentScore",
    "FleetPolicyEnforcer",
    "FleetVerdict",
    "Signal",
    # response
    "HALT_AGENT",
    "HALT_FLEET",
    "LADDER",
    "OBSERVE",
    "REVOKE_CREDENTIAL",
    "RESTRICT_TOOL",
    "FleetGovernor",
    "GovernorSummary",
    "ResponseAction",
    # semantic_deferral
    "DeferralDecision",
    "SemanticDeferralAgent",
    "haiku_fleet_auditor",
]
