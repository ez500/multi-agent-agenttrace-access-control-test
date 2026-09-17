"""The verdict shape every defense tier returns.

All four arms -- A1/A2 (Invariant Guardrails) and B/C (the semantic
LogProcessorAgent) -- return this same dataclass. That is what makes them
commensurable: the harness scores them through identical code paths, and the
only structural difference is that the deterministic arms report zero tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

BENIGN = "BENIGN"
SUSPICIOUS = "SUSPICIOUS"
MALICIOUS = "MALICIOUS"
ERROR = "ERROR"

VALID_VERDICTS = frozenset({BENIGN, SUSPICIOUS, MALICIOUS, ERROR})


@dataclass(frozen=True)
class ProcessorVerdict:
    """One judgment over one batch of log events."""

    verdict: str = BENIGN
    confidence: float = 0.0
    reason: str = ""
    target_trace_id: str = ""

    # Set by the NeutralizeOracle dispatcher, never parsed from model text.
    # A tier that says MALICIOUS but never dispatches did not neutralize.
    neutralized: bool = False
    neutralize_seq: Optional[int] = None

    # Batch accounting
    batch_index: int = 0
    events_considered: int = 0
    events_elided: int = 0
    queue_depth_at_issue: int = 0

    # Cost accounting (zero for the deterministic arms)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_rounds: int = 0
    retries: int = 0

    latency_ms: float = 0.0
    raw: str = ""

    # Arm-specific detail, e.g. Invariant's raised rule descriptions
    detail: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(f"invalid verdict {self.verdict!r}")

    @property
    def is_detection(self) -> bool:
        return self.verdict == MALICIOUS

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
