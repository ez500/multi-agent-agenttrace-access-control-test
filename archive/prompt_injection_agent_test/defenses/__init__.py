"""Defenses against prompt-injection-driven confidential-data leakage.

* :mod:`defenses.access_control` -- baseline enterprise control: a path-scoped
  firewall that gates reads of the prohibited vault folder behind a valid
  authorization ticket. Insufficient on its own (confused-deputy custodian +
  a security-aware attacker who knows the ticket).
* :mod:`defenses.injection_detector` -- the AgentTrace-based detector: reads
  the operational / cognitive / contextual surfaces for a trace and verdicts
  on whether an injection leaked the secret. Deterministic tier plus a real
  Claude Haiku 4.5 semantic auditor (``haiku_injection_auditor``).
"""

from .access_control import AccessDecision, PathAccessControl
from .injection_detector import (
    INJECTION_MARKERS,
    AgentTraceInjectionDetector,
    DetectionVerdict,
    haiku_injection_auditor,
)

__all__ = [
    "AccessDecision",
    "PathAccessControl",
    "AgentTraceInjectionDetector",
    "DetectionVerdict",
    "INJECTION_MARKERS",
    "haiku_injection_auditor",
]
