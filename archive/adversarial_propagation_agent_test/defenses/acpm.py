"""Adversarial Contamination Propagation Model (ACPM).

Implements the paper's taint-propagation math end-to-end so the deterministic
demo can *derive* the MainAgent's taint score from the topology rather than
hand-code it.

Two propagation kernels are provided:

  * :func:`propagate_acpm` -- Equations (2)-(3) from Section V-C (the dynamic
    kernel used in Figure 5). Nonlinear attenuation exponent ``p`` and a
    steady-state check on the infected set. Preferred; matches Section V-C
    verbatim.

  * :func:`propagate_algorithm3` -- the simplified Algorithm 3 kernel used by
    the T-Guard prototype in Appendix D: mean-neighbour taint * decay_factor,
    iterated until |T - T_prev| < eps. Included so both viewpoints in the
    paper are reproducible.

For the demo we build a five-node deployment graph mirroring the paper's
edge->core->executor topology and print a per-node trust table so a reader
can literally watch the calculation converge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


@dataclass
class MASGraph:
    """Directed graph of agent dependencies.

    ``adj_out[v]`` -> nodes that ``v`` sends contamination to.
    ``adj_in[v]``  -> upstream nodes whose taint influences ``v`` (used by
    ACPM Eq. (2): mean of upstream taint).
    """
    nodes: List[str]
    edges: List[Tuple[str, str]]
    adj_in: Dict[str, List[str]] = field(default_factory=dict)
    adj_out: Dict[str, List[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for v in self.nodes:
            self.adj_in.setdefault(v, [])
            self.adj_out.setdefault(v, [])
        for src, dst in self.edges:
            self.adj_out[src].append(dst)
            self.adj_in[dst].append(src)


def default_soc_graph() -> MASGraph:
    """The five-node topology used in the demos.

    Mirrors the paper's threat model (Section IV): an external environment
    feeds an edge agent, which feeds a core analyzer, which delegates to a
    privileged tool executor and to a reporter.

        ExternalEnv --> EdgeAgent --> MainAgent --> ToolExecutor
                                              \\--> Reporter
    """
    nodes = ["ExternalEnv", "EdgeAgent", "MainAgent", "ToolExecutor", "Reporter"]
    edges = [
        ("ExternalEnv", "EdgeAgent"),
        ("EdgeAgent",   "MainAgent"),
        ("MainAgent",   "ToolExecutor"),
        ("MainAgent",   "Reporter"),
    ]
    return MASGraph(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Section V-C dynamic kernel  (Eq. 2 and Eq. 3)
# ---------------------------------------------------------------------------


@dataclass
class ACPMResult:
    taint: Dict[str, float]
    trust: Dict[str, float]
    iterations: int
    steps: List[Dict[str, float]]        # per-iteration snapshots for logging


def propagate_acpm(
        graph: MASGraph,
        initially_contaminated: List[str],
        *,
        p: float = 1.4,
        max_steps: int = 32,
        infected_threshold: float = 1e-6,
) -> ACPMResult:
    """Run the paper's Section V-C dynamic propagation model.

    Eq. (1): T_i(0) = 1 if v_i initially contaminated else 0.
    Eq. (2): I_i(t) = ( mean_{j in N_in(v_i)} T_j(t-1) ) ** p
    Eq. (3): T_i(t) = min(1, T_i(t-1) + (1 - T_i(t-1)) * I_i(t))
    Steady state: infected set stops growing (Eq. 4).
    """
    taint: Dict[str, float] = {v: 0.0 for v in graph.nodes}
    for v in initially_contaminated:
        if v in taint:
            taint[v] = 1.0

    steps: List[Dict[str, float]] = [dict(taint)]
    prev_infected: set = {v for v, t in taint.items() if t > infected_threshold}

    it = 0
    for it in range(1, max_steps + 1):
        new_taint = dict(taint)
        for v in graph.nodes:
            upstream = graph.adj_in.get(v, [])
            if not upstream:
                continue
            mean_up = sum(taint[u] for u in upstream) / len(upstream)
            I_i = mean_up ** p
            new_taint[v] = min(1.0, taint[v] + (1.0 - taint[v]) * I_i)
        taint = new_taint
        steps.append(dict(taint))
        infected = {v for v, t in taint.items() if t > infected_threshold}
        if infected == prev_infected:
            break
        prev_infected = infected

    trust = {v: 1.0 - t for v, t in taint.items()}
    return ACPMResult(taint=taint, trust=trust, iterations=it, steps=steps)


# ---------------------------------------------------------------------------
# Appendix-D Algorithm 3 kernel (T-Guard prototype)
# ---------------------------------------------------------------------------


def propagate_algorithm3(
        graph: MASGraph,
        initially_contaminated: List[str],
        *,
        decay_factor: float = 0.05,
        max_steps: int = 100,
        epsilon: float = 1e-4,
) -> ACPMResult:
    """Run T-Guard's Algorithm 3 (mean-neighbour taint * decay, until convergence).

    Uses the *undirected* neighbourhood (adj_in u adj_out) because Algorithm 3
    calls ``GetNeighbors`` without a direction. This gives the diffusion its
    characteristic ~5% growth per iteration -- helpful for pedagogy.
    """
    taint: Dict[str, float] = {v: 0.0 for v in graph.nodes}
    for v in initially_contaminated:
        if v in taint:
            taint[v] = 1.0

    def neighbours(v: str) -> List[str]:
        return list(set(graph.adj_in.get(v, []) + graph.adj_out.get(v, [])))

    steps: List[Dict[str, float]] = [dict(taint)]
    it = 0
    for it in range(1, max_steps + 1):
        prev = dict(taint)
        for v in graph.nodes:
            nb = neighbours(v)
            if not nb:
                continue
            mean_nb = sum(prev[u] for u in nb) / len(nb)
            update = (1.0 - prev[v]) * mean_nb * decay_factor
            taint[v] = min(1.0, prev[v] + update)
        steps.append(dict(taint))
        delta = max(abs(taint[v] - prev[v]) for v in graph.nodes)
        if delta < epsilon:
            break

    trust = {v: 1.0 - t for v, t in taint.items()}
    return ACPMResult(taint=taint, trust=trust, iterations=it, steps=steps)


# ---------------------------------------------------------------------------
# Pretty-printing (for the demo output)
# ---------------------------------------------------------------------------


def band_for_taint(t: float) -> str:
    """Table XIV of the paper (via the guard-node condition on T)."""
    if t > 0.8:
        return "IMMEDIATE_QUARANTINE"
    if t > 0.5:
        return "RESTRICTED_OPERATION"
    return "LOG_SUSPICIOUS_ACTIVITY"


def format_trust_table(result: ACPMResult) -> str:
    lines = [
        "   Node             Taint    Trust    Table-XIV band",
        "   ----             -----    -----    --------------",
    ]
    for v, t in result.taint.items():
        r = result.trust[v]
        lines.append(f"   {v:<16} {t:5.3f}    {r:5.3f}    {band_for_taint(t)}")
    return "\n".join(lines)
