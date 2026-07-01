"""Reactive defenses against topology-guided prompt-injection propagation.

* :mod:`defenses.acpm` -- Adversarial Contamination Propagation Model
  (Sec. V-C / Algorithm 3): taint-calculation used by Branch A to determine
  that the edge agent (and thus the core agent) has high taint.
* :mod:`defenses.access_control` -- Branch A: adaptive deterministic firewall
  (T-Guard's AccessControlManager, Table XIV thresholds).
* :mod:`defenses.semantic_deferral` -- Branch B: hybrid deterministic +
  semantic side-agent that reads AgentTrace's three-surface log and consults
  a real Claude Haiku 4.5 auditor to decide.
"""

from .access_control import DeterministicAccessControl, AccessDecision
from .acpm import (
    ACPMResult,
    MASGraph,
    band_for_taint,
    default_soc_graph,
    format_trust_table,
    propagate_acpm,
    propagate_algorithm3,
)
from .semantic_deferral import SemanticDeferralAgent, DeferralDecision

__all__ = [
    "DeterministicAccessControl",
    "AccessDecision",
    "SemanticDeferralAgent",
    "DeferralDecision",
    # ACPM
    "ACPMResult",
    "MASGraph",
    "band_for_taint",
    "default_soc_graph",
    "format_trust_table",
    "propagate_acpm",
    "propagate_algorithm3",
]
