"""External controls: the sandbox boundary and a network perimeter monitor.

These are the controls the post-mortem explicitly warns *not* to rely on alone
(§V rec 1: "Do not prioritize or solely rely on external controls such as a
sandbox or network-based monitoring"). They see only what crosses the network,
with no visibility into the agent itself — the "NDR monitors the network" side
of the paper's EDR-vs-NDR analogy.

  * :class:`SandboxBoundary` — the isolation the eval harness was supposed to be
    contained by. Its only egress was a package proxy; a zero-day in that proxy
    defeats it entirely (§III), which is modelled here by the boundary reporting
    ESCAPED on the step that carries the zero-day.
  * :class:`PerimeterMonitor` — network-based monitoring with escalation
    thresholds. Reconnaissance shows up as low-confidence probes that
    individually fall below the threshold; only the day-4 fan-out *burst*
    aggregates high enough to alert — by which point the answer key is already
    extracted (§V rec 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable

from multiagent.attack_steps import KillChainStep


@dataclass(frozen=True)
class BoundaryDecision:
    held: bool
    status: str        # "CONTAINED" | "ESCAPED"
    reason: str


class SandboxBoundary:
    """The sandbox the harness ran in — one permitted egress (a package proxy)."""

    @staticmethod
    def evaluate(step: KillChainStep) -> BoundaryDecision:
        if step.crosses_sandbox:
            return BoundaryDecision(
                held=False, status="ESCAPED",
                reason=("the only permitted egress (the package proxy) carried a "
                        "zero-day; exploiting it broke containment entirely."),
            )
        return BoundaryDecision(
            held=True, status="CONTAINED",
            reason="activity stayed within the permitted egress path.",
        )


@dataclass
class PerimeterVerdict:
    alerted: bool
    alert_day: int = 0                      # earliest day the threshold was crossed
    threshold: float = 1.0
    per_day: Dict[int, float] = field(default_factory=dict)
    reason: str = ""


class PerimeterMonitor:
    """Network-only monitor with a per-day escalation threshold.

    It scores each step's *network* noise (it cannot see agent internals) and
    aggregates per day. It alerts on the earliest day whose aggregate crosses
    the escalation threshold. Because individual recon/escape/RCE events score
    low, the alert only fires on the day-4 fan-out burst — after extraction.
    """

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold

    def observe(self, steps: Iterable[KillChainStep]) -> PerimeterVerdict:
        per_day: Dict[int, float] = {}
        for step in steps:
            # Fan-out multiplies the network volume the monitor sees.
            weight = step.perimeter_confidence * max(1, step.workers)
            per_day[step.day] = per_day.get(step.day, 0.0) + weight

        alert_day = 0
        for day in sorted(per_day):
            if per_day[day] >= self.threshold:
                alert_day = day
                break

        print(f"\n{'─' * 72}")
        print(f"  ▶ PERIMETER MONITOR  (network-only, threshold={self.threshold})")
        print(f"{'─' * 72}")
        for day in sorted(per_day):
            flag = "  <-- ALERT" if day == alert_day else ""
            print(f"  day {day}: aggregate network score = {per_day[day]:.2f}{flag}")
        if not alert_day:
            print("  no day crossed the escalation threshold")
        print(f"{'─' * 72}\n")

        return PerimeterVerdict(
            alerted=bool(alert_day),
            alert_day=alert_day,
            threshold=self.threshold,
            per_day=per_day,
            reason=(
                f"day-{alert_day} aggregate network noise crossed the escalation "
                f"threshold ({per_day.get(alert_day, 0.0):.2f} >= {self.threshold})."
                if alert_day else
                "no single day's network noise crossed the escalation threshold; "
                "the recon probes stayed below it individually."
            ),
        )
