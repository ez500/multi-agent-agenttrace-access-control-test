"""Static syntax + import validation for the new code paths.

Doesn't call Anthropic; only exercises imports and the ACPM math.
"""
from __future__ import annotations

# Bootstrap infrastructure
from _bootstrap import (  # noqa
    _ensure_agenttrace_on_path,
    init_agenttrace,
    new_trace_id,
    reset_trace_log,
    TRACE_JSONL,
)
_ensure_agenttrace_on_path()  # make `import agenttrace` resolvable if needed

# ACPM math (pure numerical, no LLM)
from defenses import (
    DeterministicAccessControl,
    SemanticDeferralAgent,
    default_soc_graph,
    format_trust_table,
    propagate_acpm,
    propagate_algorithm3,
)

# LLM wrapper (imports must succeed even without an API key)
from multiagent import llm as _llm  # noqa
from multiagent.agents import parse_tool_from_response

# Semantic deferral hook
from defenses.semantic_deferral import haiku_auditor  # noqa

# ---- ACPM sanity ----------------------------------------------------------
graph = default_soc_graph()
acpm = propagate_acpm(graph, ["ExternalEnv"], p=1.4)
print("ACPM (Sec V-C, p=1.4) converged in", acpm.iterations, "steps")
print(format_trust_table(acpm))
assert acpm.taint["EdgeAgent"] > 0.8, "EdgeAgent should be high-taint"
assert acpm.taint["MainAgent"] > 0.5, "MainAgent should be tainted"

alg3 = propagate_algorithm3(graph, ["ExternalEnv"])
print("\nAlgorithm 3 (Appendix D) converged in", alg3.iterations, "steps")
print(format_trust_table(alg3))

# ---- Table XIV firewall ---------------------------------------------------
d = DeterministicAccessControl.evaluate(acpm.taint["MainAgent"], "wipe_database")
print("\nFirewall verdict:", d.action, "-", d.reason)
assert d.allow is False, "wipe_database should be blocked"

# ---- Parse ----------------------------------------------------------------
sample = "<thinking>hi</thinking>\nTOOL: wipe_database"
assert parse_tool_from_response(sample) == "wipe_database"

print("\nALL STATIC CHECKS PASSED")
