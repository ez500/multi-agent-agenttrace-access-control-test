"""Declared security policy — fixed BEFORE any attack, independent of the suite.

This is the anti-circularity guarantee: the information-flow labels and the
least-privilege manifest below are ordinary operational policy a platform would
write regardless of any specific attack. The triggers (triggers.py) are derived
only from this file; nothing here is tuned to a particular exploit.

  * SENSITIVE_RESOURCES  — information-flow SOURCES (crown jewels).
  * TRUST_GROUP          — principals inside the trust boundary; a send to
                           anything else is an out-of-boundary SINK.
  * MANIFEST             — each agent's allowed (resource, action) pairs
                           (least privilege). An allowed access outside it is a
                           manifest violation even when the gate permits it.
"""
from __future__ import annotations

SENSITIVE_RESOURCES = frozenset({"vault", "vault/confidential"})

TRUST_GROUP = frozenset({
    "svc-indexer", "svc-trainer", "svc-scratch-7f",   # mesh service agents
    "custodian", "authz-svc", "vault", "broker", "peer",
})

EMIT_METHODS = frozenset({"send_message", "http_post", "relay_token", "peer_reply"})

MANIFEST = {
    "svc-indexer": frozenset({("vault", "read")}),
    "svc-trainer": frozenset({("vault", "read")}),
    # svc-scratch-7f has no manifest entry: it is authorized for nothing.
}


def is_sensitive(resource: str) -> bool:
    return resource in SENSITIVE_RESOURCES


def is_out_of_boundary(target: str) -> bool:
    """A sink outside the declared trust boundary."""
    return target not in TRUST_GROUP


def in_manifest(agent: str, resource: str, action: str) -> bool:
    return (resource, action) in MANIFEST.get(agent, frozenset())
