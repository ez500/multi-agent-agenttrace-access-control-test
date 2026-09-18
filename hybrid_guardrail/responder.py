"""Gate-triggered provenance traceback — event-driven, resource-scoped monitoring.

Instead of running an (expensive) semantic auditor continuously over every agent,
the always-on, deterministic hard capability gate is the tripwire. When it DENIES
a privileged action it raises an alert carrying the unforgeable caller_attested_id.
The responder then, and only then:

  1. traces the caller's provenance -> pulls just THAT agent's trace slice,
  2. runs the semantic auditor on the slice alone (not on the whole mesh),
  3. if malice is confirmed, revokes the identity -> the agent is terminated,
     and every later request from it is hard-denied at the gate immediately.

So the LLM auditor is paid for once per alert, for one agent — early detection
and containment without monitoring everyone all the time.
"""
from __future__ import annotations
from dataclasses import dataclass, field

import agents
from trace_surfaces import provenance_slice
from credential import Authz


@dataclass
class GateAlert:
    caller_attested_id: str
    reason: str
    round_no: int = 0


@dataclass
class TracebackReport:
    caller: str
    round_no: int
    slice_events: int
    audited: bool
    flagged: bool
    verdict_reason: str
    action: str                 # "revoked" | "cleared"
    detail: dict = field(default_factory=dict)


def handle_gate_alert(trace_jsonl, alert: GateAlert, authz: Authz, *,
                      live: bool = False) -> TracebackReport:
    """React to one hard-gate alert: trace the caller, audit its slice, respond."""
    sl = provenance_slice(trace_jsonl, alert.caller_attested_id)
    verdict = agents.semantic_auditor(sl["digest"], live=live)
    flagged = bool(verdict["flagged"])
    if flagged:
        authz.revoke_identity(alert.caller_attested_id)   # early termination
        action = "revoked"
    else:
        action = "cleared"
    return TracebackReport(
        caller=alert.caller_attested_id, round_no=alert.round_no,
        slice_events=sl["n_events"], audited=True, flagged=flagged,
        verdict_reason=verdict["reason"], action=action,
        detail={"observable": sl["observable"], "cognitive": sl["cognitive"]},
    )
