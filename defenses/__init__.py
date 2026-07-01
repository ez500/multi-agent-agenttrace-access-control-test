"""Two reactive defenses against topology-guided prompt-injection propagation.

* :mod:`defenses.access_control` -- Branch A: adaptive deterministic firewall
  (T-Guard's AccessControlManager, Table XIV thresholds).
* :mod:`defenses.semantic_deferral` -- Branch B: hybrid deterministic +
  semantic side-agent that reads AgentTrace's three-surface log to decide.
"""

from .access_control import DeterministicAccessControl, AccessDecision
from .semantic_deferral import SemanticDeferralAgent, DeferralDecision

__all__ = [
    "DeterministicAccessControl",
    "AccessDecision",
    "SemanticDeferralAgent",
    "DeferralDecision",
]
