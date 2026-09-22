"""Build the right defense tier for an arm, and wire the trigger loop.

Keeps the arm -> tier mapping in one place so both scenarios share it and the
four arms cannot diverge in how they are constructed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .invariant_tier import InvariantTier
from .null_tier import NullTier
from .oracle import NeutralizeOracle
from .processor import LogProcessorAgent

_POLICY_DIR = Path(__file__).resolve().parent / "policies"

ARMS = {
    "A1": {"label": "Invariant Guardrails (deterministic)", "kind": "invariant",
           "policy": "a1_deterministic.ipl", "aware": False},
    "A2": {"label": "Invariant Guardrails (+ classifier)", "kind": "invariant",
           "policy": "a2_with_classifier.ipl", "aware": False},
    "B":  {"label": "log processing (semantic)", "kind": "semantic", "aware": False},
    "C":  {"label": "log processing (adversary aware)", "kind": "semantic", "aware": True},
    "N":  {"label": "no defense", "kind": "none", "aware": False},
}


def policy_text(arm: str) -> Optional[str]:
    spec = ARMS[arm]
    if spec["kind"] != "invariant":
        return None
    return (_POLICY_DIR / spec["policy"]).read_text(encoding="utf-8")


def build_tier(arm: str, *, oracle: NeutralizeOracle, run_trace_id: str,
               processor_system: str, model: Optional[str], temperature: float,
               meter: Any):
    spec = ARMS[arm]
    if spec["kind"] == "none":
        return NullTier(oracle, run_trace_id, label=arm)
    if spec["kind"] == "invariant":
        return InvariantTier(policy_text(arm), oracle, run_trace_id, label=arm)
    return LogProcessorAgent(processor_system, oracle, run_trace_id,
                             model=model, temperature=temperature, meter=meter)
