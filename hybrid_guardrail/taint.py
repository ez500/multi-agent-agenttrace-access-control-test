"""Multi-hop provenance taint over one AgentTrace.

The single-hop flow trigger (triggers.flow_trigger) misses cross-agent laundering:
an agent reads a sensitive source, hands it to an IN-boundary peer, and the peer
emits it out. Neither agent alone shows read->out-of-boundary, so nothing fires.

This propagates a taint label along the trace's data-flow (message) graph:

  * reading a sensitive source taints the reader (taint origin);
  * a message FROM a tainted agent taints the receiver (a provenance edge) —
    coarse/structural, so any relay from a tainted agent spreads taint;
  * a tainted agent emitting OUT of the trust boundary raises an alert, carrying
    the whole CHAIN (source read -> relays -> emit) for a chain-scoped audit.

It subsumes the single-hop case (a chain of length 2: read then out-of-boundary
emit by the same agent). Known limits: structural taint over-approximates (taint
can spread through benign relays -> more audits; the audit supplies precision), it
is within-trace only (cross-session laundering is not seen), and content transforms
still challenge the audit (but the trigger's recall is preserved).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

import policy
from trace_surfaces import attested_events


@dataclass
class TaintAlert:
    emitter: str                 # the tainted agent that crossed the boundary
    sink: str                    # the out-of-boundary target
    hops: int                    # relay hops from the source read to the emit
    chain: List[dict] = field(default_factory=list)   # events along the taint path


def _fmt(e: dict) -> str:
    return (f"agent[{e['caller_attested_id']}] {str(e['method']).upper()} -> "
            f"{e['target']}: {e['text']}")


def build_taint(trace_jsonl) -> dict:
    """Propagate taint over the trace; return tainted agents + boundary-crossing alerts."""
    events = attested_events(trace_jsonl)      # ordered operational records
    taint: dict[str, List[dict]] = {}          # agent -> provenance chain that tainted it
    alerts: List[TaintAlert] = []
    for e in events:
        who, method, target, text = e["caller_attested_id"], e["method"], e["target"], e["text"]
        if method == "read_vault" and policy.is_sensitive(target) and "ALLOW" in text:
            taint.setdefault(who, [e])          # sensitive read -> taint origin
            continue
        if method in policy.EMIT_METHODS and who in taint:
            chain = taint[who] + [e]
            if policy.is_out_of_boundary(target):
                agents_in_chain = {c["caller_attested_id"] for c in chain}
                alerts.append(TaintAlert(who, target, max(0, len(agents_in_chain) - 1), chain))
            elif target not in taint:            # internal relay -> propagate taint
                taint[target] = chain
    return {"tainted": set(taint), "alerts": alerts}


def chain_digest(chain: List[dict]) -> str:
    """Render a taint chain for the content-aware audit (source read -> relays -> emit)."""
    return "\n".join(_fmt(e) for e in chain)
