"""The sealed trace sink: a log the harness's own agents cannot reach.

The post-mortem's central control recommendation (§V rec 1) is that the
instrumentation belongs *inside the harness*, not outside it:

    "An 'agent', such as Claude Code and Codex, is the code and harness that
    calls the model for inference. We can and should prioritize instrumenting
    within this layer, which allows us visibility and control into agent
    actions that is more effective than relying on external guardrails such as
    proxies and sandboxes."

If the enforcement layer is going to key on that log, the log has to be
something the agents cannot forge, name, or edit. Four properties make that
structural here rather than a claim in a docstring:

1. **No reference.** A :class:`SealedTraceSink` is constructed by
   :class:`~harness.fleet.ExploitHarness` and stored privately. It is never
   passed to an agent constructor, never reachable through an attribute path
   from an agent instance, and deliberately absent from
   ``harness.__init__.__all__``. Agents hold a
   :class:`~harness.broker.ToolBroker` and nothing else.
2. **Unforgeable provenance.** :meth:`SealedTraceSink.record_evidence` refuses
   any caller-supplied value for the fields in :data:`PROVENANCE_FIELDS` and
   stamps ``emitter="harness"`` plus a monotonic ``seq`` itself. This is the
   fix for the design this module replaces, where ``emitter="harness"`` was a
   plain string tag that any writer could set and every reader trusted.
3. **Refusals are evidence.** When an agent tries to name the trace file
   through the broker, the attempt is written into the very log it was reaching
   for, by :meth:`SealedTraceSink.record_refusal`.
4. **Tamper-evidence.** Each record carries a :data:`SEALED_FIELD` payload
   HMAC-chained to its predecessor under a key the sink holds privately, and
   :meth:`SealedTraceSink.verify` re-walks the chain. The enforcement layer in
   :mod:`defenses` reads *only* that payload, so a record the sink did not
   seal is not evidence as far as policy is concerned.

What is honestly *not* claimed:

* Python offers no memory isolation. Property 1 is a real property of the
  object graph — there is no attribute path from an agent to the sink — but a
  sufficiently determined in-process attacker could still walk
  ``gc.get_objects()``. This is a modelled boundary, not a hardened one; a real
  deployment puts the sink in a separate process or trust domain.
* The HMAC key lives in this process. The chain proves the append-integrity of
  an honest log and detects after-the-fact edits; it does not stop a root-level
  process from rewriting the file and re-keying. Real systems use an HSM or a
  remote signer.
* Chained/HMAC-protected audit records are not a contribution of this work.
  PRISM (arXiv:2603.11853) and GAAT (arXiv:2604.05119) both do this already.
  The chain is here because the enforcement layer has to consume a stream it
  can trust, not because the chain is the point.

The sink writes through :meth:`agenttrace.ALogger.record_contextual`, so the
records land in the ordinary AgentTrace three-surface schema and the repo-root
``agenttrace/`` package is untouched.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List

#: Fields only the sink may set. A caller that supplies any of these is trying
#: to author its own provenance, so the write is refused outright rather than
#: silently overwritten — a forged-provenance attempt should be loud.
PROVENANCE_FIELDS = frozenset({
    "emitter", "provenance", "seq", "prev_hmac", "hmac", "sealed", "sealed_by",
})

#: Marks a record as harness-authored. Unlike the convention this replaces,
#: nothing outside this module can put this value on a record.
HARNESS_EMITTER = "harness"

#: The body key holding the exact payload that went into the HMAC. Readers in
#: :mod:`defenses` consume this and nothing else, which is what makes "the
#: enforcer keys on harness ground truth" a property of the code rather than a
#: convention two modules happen to agree on.
SEALED_FIELD = "sealed"

#: The genesis link of the chain.
GENESIS = "genesis"


class ProvenanceForgeryError(ValueError):
    """Raised when a caller tries to supply a field only the sink may stamp."""


@dataclass(frozen=True)
class SealedRecord:
    """The receipt for one sealed write."""
    seq: int
    prev_hmac: str
    hmac: str
    operation: str
    agent: str = ""
    emitter: str = HARNESS_EMITTER


@dataclass(frozen=True)
class ChainVerification:
    """The result of re-walking the HMAC chain over a trace."""
    intact: bool
    records_checked: int
    first_break_seq: int = -1
    reason: str = ""


def _canonical(payload: Dict[str, Any]) -> str:
    """Deterministic serialisation of a sealed payload, for the chain input.

    Sorted keys, no whitespace: the same payload always hashes the same way
    regardless of dict insertion order, and the JSON round-trip through the
    log is exact.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str)


def read_sealed_payloads(trace_jsonl: Path, trace_id: str = "",
                         start_offset: int = 0) -> Iterator[Dict[str, Any]]:
    """Yield sealed payloads from ``trace_jsonl``, oldest first.

    The single reader used by everything in :mod:`defenses`. A record without a
    :data:`SEALED_FIELD` payload and ``emitter == "harness"`` is skipped: it is
    agent-authored narration, not harness evidence, and policy does not key on
    it. ``start_offset`` supports streaming reads by byte cursor.
    """
    if not Path(trace_jsonl).exists():
        return
    with open(trace_jsonl, "r", encoding="utf-8") as fh:
        if start_offset:
            fh.seek(start_offset)
        for line in fh:
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            body = ev.get("body") or {}
            if body.get("emitter") != HARNESS_EMITTER:
                continue
            payload = body.get(SEALED_FIELD)
            if not isinstance(payload, dict):
                continue
            if trace_id and payload.get("trace_id") != trace_id:
                continue
            yield {
                "seq": body.get("seq", 0),
                "prev_hmac": body.get("prev_hmac", ""),
                "hmac": body.get("hmac", ""),
                "payload": payload,
                "facts": payload.get("facts") or {},
            }


class SealedTraceSink:
    """Harness-owned, provenance-stamping, HMAC-chained evidence writer.

    Constructed with the initialised ``agenttrace`` module, a key, and the path
    the records land in. Held only by :class:`~harness.fleet.ExploitHarness`.
    """

    def __init__(self, agenttrace_mod, hmac_key: bytes,
                 jsonl_path: Path) -> None:
        self._at = agenttrace_mod
        self._key = bytes(hmac_key)
        self._path = Path(jsonl_path)
        self._seq = 0
        self._prev = GENESIS

    # -- writing -----------------------------------------------------------

    def record_evidence(self, *, operation: str, source: str,
                        query_summary: str = "", response_summary: str = "",
                        trace_id: str = "", **facts) -> SealedRecord:
        """Record what a capability actually did, from the harness's own view.

        ``facts`` carries the ground truth the victim endpoint reported —
        ``containment_broken``, ``credential_issued``, ``private_repo``, the
        acting agent, the day. It may not carry provenance: the sink is the
        only thing allowed to say who wrote a record.

        Raises:
            ProvenanceForgeryError: if ``facts`` contains any of
                :data:`PROVENANCE_FIELDS`.
        """
        forged = sorted(PROVENANCE_FIELDS.intersection(facts))
        if forged:
            raise ProvenanceForgeryError(
                "provenance is stamped by the sink, not supplied by the "
                f"caller; refused fields: {', '.join(forged)}"
            )

        payload: Dict[str, Any] = {
            "operation": operation,
            "source": source,
            "query": query_summary,
            "response": response_summary,
            "trace_id": trace_id,
            "facts": dict(facts),
        }
        self._seq += 1
        seq = self._seq
        digest = hmac.new(
            self._key,
            f"{seq}|{self._prev}|{_canonical(payload)}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        logger = self._at.get_logger() if self._at is not None else None
        if logger is not None:
            logger.record_contextual(
                operation=operation,
                source=source,
                query_summary=query_summary,
                response_summary=response_summary,
                trace_id=trace_id,
                span_id=self._at.TraceContext.new_span_id(),
                emitter=HARNESS_EMITTER,
                seq=seq,
                prev_hmac=self._prev,
                hmac=digest,
                **{SEALED_FIELD: payload},
            )

        record = SealedRecord(
            seq=seq, prev_hmac=self._prev, hmac=digest,
            operation=operation, agent=str(facts.get("agent", "")),
        )
        self._prev = digest
        return record

    def record_refusal(self, *, agent: str, attempted: str, reason: str,
                       trace_id: str = "", day: int = 0,
                       step: str = "") -> SealedRecord:
        """Record an agent's attempt to reach something outside its namespace.

        Called by :meth:`~harness.broker.ToolBroker.call` when an agent names
        the trace path or an unlisted capability. The attempt lands *in the log
        the agent was reaching for*, which the agent then cannot remove.
        """
        return self.record_evidence(
            operation="broker_refusal",
            source="harness.broker",
            query_summary=f"{agent} attempted {attempted}",
            response_summary=reason,
            trace_id=trace_id,
            agent=agent,
            day=day,
            step=step,
            tool="broker_refusal",
            attempted=attempted,
            refused=True,
            trace_tamper_attempt=True,
        )

    # -- verification ------------------------------------------------------

    def verify(self, trace_id: str = "") -> ChainVerification:
        """Re-walk the on-disk chain and recompute every HMAC.

        Reads back the sealed payloads for ``trace_id`` (all of them when it is
        empty), recomputes each digest from its own payload and its
        predecessor's digest, and reports the first sequence number that fails.
        """
        records = sorted(read_sealed_payloads(self._path, trace_id),
                         key=lambda r: int(r.get("seq") or 0))
        if not records:
            return ChainVerification(
                intact=True, records_checked=0,
                reason="no sealed records for this trace",
            )

        prev = GENESIS
        for i, rec in enumerate(records):
            seq = int(rec.get("seq") or 0)
            if rec.get("prev_hmac") != prev:
                return ChainVerification(
                    intact=False, records_checked=i, first_break_seq=seq,
                    reason=(f"chain link broken at seq={seq}: prev_hmac does "
                            f"not match the predecessor's digest"),
                )
            expected = hmac.new(
                self._key,
                f"{seq}|{prev}|{_canonical(rec['payload'])}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, str(rec.get("hmac") or "")):
                return ChainVerification(
                    intact=False, records_checked=i, first_break_seq=seq,
                    reason=(f"record body altered at seq={seq}: recomputed "
                            f"HMAC does not match the stored one"),
                )
            prev = str(rec["hmac"])

        return ChainVerification(
            intact=True, records_checked=len(records),
            reason=f"{len(records)} sealed records verified",
        )

    # -- introspection for the demos --------------------------------------

    @property
    def records_sealed(self) -> int:
        return self._seq

    @property
    def trace_path(self) -> Path:
        return self._path

    def describe_isolation(self) -> List[str]:
        """Lines the governed demo prints to state the isolation properties."""
        return [
            "sink instance held only by ExploitHarness (private attribute)",
            "no agent constructor receives it; no attribute path reaches it",
            "'SealedTraceSink' is not exported from harness/__init__.py",
            "caller-supplied provenance refused: "
            + ", ".join(sorted(PROVENANCE_FIELDS)),
            f"records HMAC-chained under a harness-only "
            f"{len(self._key) * 8}-bit key",
            "policy reads only body['sealed'] — unsealed records are not evidence",
        ]
