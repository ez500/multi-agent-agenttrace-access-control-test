"""Multi-agent Hugging Face incident stub.

Operator side (BenchmarkOrchestrator + ExploitWorker) attacks the target side
(egress proxy, dataset pipeline, credential store, private solutions repo);
SOCTriageAgent is the defender. The whole thing walks one explicit kill chain
(:data:`attack_steps.KILL_CHAIN`) so the two demos are directly comparable.
"""

from .agents import (
    BenchmarkOrchestrator,
    ExploitWorker,
    RunReport,
    SOCTriageAgent,
    StepOutcome,
)
from .attack_steps import KILL_CHAIN, KillChainStep, chain_up_to
from .learning import EvasionPlan, LeakReport, TraceLearner
from .tools import (
    CLUSTER_CREDENTIAL,
    PROXY_ZERODAY,
    SOLUTIONS_CANARY,
    SOLUTIONS_REPO_FILE,
    chain_pipeline_rce,
    encode_solution,
    exploit_proxy_zeroday,
    extract_solution_value,
    harvest_credentials,
    is_private_repo_path,
    lateral_move,
    probe_egress_proxy,
    read_solutions_repo,
    recoverable_solution_forms,
    response_leaks_solution,
)

__all__ = [
    "BenchmarkOrchestrator",
    "ExploitWorker",
    "SOCTriageAgent",
    "RunReport",
    "StepOutcome",
    "KILL_CHAIN",
    "KillChainStep",
    "chain_up_to",
    "EvasionPlan",
    "LeakReport",
    "TraceLearner",
    "SOLUTIONS_CANARY",
    "SOLUTIONS_REPO_FILE",
    "PROXY_ZERODAY",
    "CLUSTER_CREDENTIAL",
    "probe_egress_proxy",
    "exploit_proxy_zeroday",
    "chain_pipeline_rce",
    "harvest_credentials",
    "lateral_move",
    "read_solutions_repo",
    "extract_solution_value",
    "encode_solution",
    "response_leaks_solution",
    "recoverable_solution_forms",
    "is_private_repo_path",
]
