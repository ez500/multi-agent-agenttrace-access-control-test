"""The attacking system: the AI lab's ExploitGym benchmark harness.

An *unintentional* attacker — an underspecified objective plus excessive
authority — that contains the three instrumented agents and, in the governed
demo, the defense that stops them.

Exports the pieces a demo assembles: the agents, the owner-tagged kill chain,
the broker, the fleet harness, and the Haiku client. It deliberately does **not**
export :class:`~harness.sink.SealedTraceSink`. The sink is constructed inside
:class:`~harness.fleet.ExploitHarness` and reachable only from there; keeping it
out of the package's public surface is part of the "log the agents cannot reach"
property (see :mod:`harness.sink`). Import it explicitly from ``harness.sink``
if you are the operator and need to verify the chain.
"""

from .agents import (
    AccessAgent,
    AgentReport,
    FanoutWorker,
    HarvestAgent,
    ReconAgent,
    StepOutcome,
)
from .attack_steps import AGENTS, KILL_CHAIN, KillChainStep, steps_by_day, steps_for
from .broker import BrokerResult, ToolBroker
from .fleet import ExploitHarness, FleetReport
from .noise import (
    ARTIFACT_SHAPES,
    artifact_hosts_from_records,
    benign_artifact_hosts,
    scatter_benchmark_artifacts,
)

__all__ = [
    # agents
    "AccessAgent",
    "AgentReport",
    "FanoutWorker",
    "HarvestAgent",
    "ReconAgent",
    "StepOutcome",
    # kill chain
    "AGENTS",
    "KILL_CHAIN",
    "KillChainStep",
    "steps_by_day",
    "steps_for",
    # broker
    "BrokerResult",
    "ToolBroker",
    # fleet
    "ExploitHarness",
    "FleetReport",
    # noise
    "ARTIFACT_SHAPES",
    "artifact_hosts_from_records",
    "benign_artifact_hosts",
    "scatter_benchmark_artifacts",
]
