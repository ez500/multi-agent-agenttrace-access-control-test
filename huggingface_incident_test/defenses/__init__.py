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
* :mod:`defenses.live_response` — the LIVE agent-layer control:
  :class:`LiveTraceMonitor` streams the harness-emitted telemetry *during* the
  run and actively responds (revoke credential / isolate agent) at machine
  speed. Used by ``demo_live_response.py``.
"""

from .perimeter import (
    BoundaryDecision,
    PerimeterMonitor,
    PerimeterVerdict,
    SandboxBoundary,
)
from .live_response import (
    ALERT,
    ISOLATE_AGENT,
    OBSERVE,
    REVOKE_CREDENTIAL,
    SIGNALS,
    LiveTraceMonitor,
    MonitorSummary,
    ResponseAction,
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
    "LiveTraceMonitor",
    "ResponseAction",
    "MonitorSummary",
    "SIGNALS",
    "OBSERVE",
    "ALERT",
    "REVOKE_CREDENTIAL",
    "ISOLATE_AGENT",
]
