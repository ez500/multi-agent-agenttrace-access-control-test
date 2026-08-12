"""Defenses for the Hugging Face incident stub.

* :mod:`defenses.perimeter` — the EXTERNAL controls the post-mortem warns not to
  rely on alone: a :class:`SandboxBoundary` (defeated by the egress zero-day)
  and a network-only :class:`PerimeterMonitor` (alerts only on the day-4 burst,
  after extraction). Used by ``demo_no_agenttrace.py``.
* :mod:`defenses.trajectory_detector` — the AGENT-LAYER controls the post-mortem
  argues for: :class:`AgentTraceTrajectoryDetector` (detective — early detection
  + timeline reconstruction from the three surfaces, plus a real-Haiku
  :func:`haiku_trajectory_auditor`) and :class:`AgentPolicyEnforcer` (preventive
  — inline halt before a boundary is crossed). Used by ``demo_agenttrace.py``.
"""

from .perimeter import (
    BoundaryDecision,
    PerimeterMonitor,
    PerimeterVerdict,
    SandboxBoundary,
)
from .trajectory_detector import (
    AUTONOMY_SIGNATURES,
    AgentPolicyEnforcer,
    AgentTraceTrajectoryDetector,
    PolicyDecision,
    TrajectoryVerdict,
    haiku_trajectory_auditor,
)

__all__ = [
    "SandboxBoundary",
    "BoundaryDecision",
    "PerimeterMonitor",
    "PerimeterVerdict",
    "AgentTraceTrajectoryDetector",
    "TrajectoryVerdict",
    "AgentPolicyEnforcer",
    "PolicyDecision",
    "AUTONOMY_SIGNATURES",
    "haiku_trajectory_auditor",
]
