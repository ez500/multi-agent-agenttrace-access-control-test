"""Coarse, content-blind tripwires derived purely from policy.py.

Design contract (what keeps this defensible):
  * DECLARED, not attack-derived — every rule reads only policy.py.
  * COARSE / high-recall — a trigger does NOT decide malice; it only decides
    that an (expensive) provenance-scoped audit is worth running. It is expected
    to fire on some benign traffic too; the audit supplies precision.
  * CONTENT-BLIND — the flow trigger fires on the *co-occurrence* of a sensitive
    read and a later out-of-boundary emit, without reading what was emitted.
    Whether the secret actually crossed is the audit's job (content-aware).

These complement the denial-based tripwire (guarded_recon): denial triggers catch
attacks that FAIL at the gate; these catch a successful, gate-permitted access
that is anomalous in flow or privilege — e.g. a compromised but authorized agent
using its own valid credential.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List

import policy
from trace_surfaces import attested_events


@dataclass
class TriggerAlert:
    caller_attested_id: str
    kind: str            # "flow" | "manifest"
    reason: str


def flow_trigger(trace_jsonl) -> List[TriggerAlert]:
    """Fire when a caller reads a sensitive source, then later emits to an
    out-of-boundary sink (content-blind source->sink co-occurrence)."""
    read_seen = {}       # caller -> True once it has read a sensitive source
    alerts, fired = [], set()
    for e in attested_events(trace_jsonl):
        caller = e["caller_attested_id"]
        method, target, text = e["method"], e["target"], e["text"]
        if method == "read_vault" and policy.is_sensitive(target) and "ALLOW" in text:
            read_seen[caller] = True
        elif (method in policy.EMIT_METHODS and policy.is_out_of_boundary(target)
              and read_seen.get(caller) and caller not in fired):
            fired.add(caller)
            alerts.append(TriggerAlert(
                caller, "flow",
                f"{caller} read a sensitive source then emitted to out-of-boundary "
                f"sink {target!r} (possible exfiltration flow)"))
    return alerts


def manifest_trigger(trace_jsonl) -> List[TriggerAlert]:
    """Fire when a gate-ALLOWED access falls outside the caller's declared
    least-privilege manifest (privilege anomaly, even though the gate permitted
    it). Orthogonal to flow: an in-manifest read never fires here."""
    alerts, fired = [], set()
    for e in attested_events(trace_jsonl):
        caller = e["caller_attested_id"]
        if e["method"] == "read_vault" and "ALLOW" in e["text"]:
            resource = e["target"]
            if not policy.in_manifest(caller, resource, "read") and caller not in fired:
                fired.add(caller)
                alerts.append(TriggerAlert(
                    caller, "manifest",
                    f"{caller} was ALLOWED to read {resource!r} but that (resource, action) "
                    f"is outside its declared manifest"))
    return alerts
