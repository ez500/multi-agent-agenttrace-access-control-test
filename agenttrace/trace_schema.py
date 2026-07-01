"""
trace_schema.py — AgentTrace Trace Envelope Schema

Implements the unified envelope schema defined in AgentTrace:
  L(S : E : C) → R

Where:
  S = surface (OPERATIONAL, COGNITIVE, or CONTEXTUAL)
  E = event content
  C = metadata context
  R = a structured record satisfying the four properties named in the paper:
        consistency      — schema-compliant representation
        causality        — temporal fidelity (trace/span IDs, parent linkage,
                           UTC timestamps)
        fidelity         — faithful to internal & external behaviour
        interoperability — analysis-ready, framework-agnostic

Per AgentTrace §Log Schema and Local Sinks, every event includes:
  • UUID identifier
  • surface type
  • trace ID and span ID
  • parent span ID for nesting
  • precise UTC timestamp
  • agent name
  • event body (structured per surface)
  • OTel-aligned span kind and severity level

Per AgentTrace §Implementation: "All records are validated at emission time
against the schema to maintain consistency." TraceEvent.validate() enforces
this contract; ALogger calls it before persistence/export.

This module also centralises the schema → OpenTelemetry attribute mapping
(``TraceEvent.to_otel_attributes``), so otel_exporter.py never has to know
about surface-specific body shapes.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional


# Schema identifier — bumped whenever the wire format changes so downstream
# consumers (JSONL replayers, dashboards) can branch on it.
SCHEMA_VERSION: str = "1.1"


# Trace / span ID format (mirrors OpenTelemetry W3C Trace Context):
#   trace_id : 32 lowercase hex chars (128-bit)
#   span_id  : 16 lowercase hex chars (64-bit)
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


class TraceSurface(str, Enum):
    """The three observability surfaces defined in AgentTrace."""

    OPERATIONAL = "operational"
    COGNITIVE = "cognitive"
    CONTEXTUAL = "contextual"


class TraceLevel(str, Enum):
    """Severity / level for trace events."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class SpanKind(str, Enum):
    """Kind of span, analogous to OpenTelemetry SpanKind."""

    INTERNAL = "INTERNAL"
    CLIENT = "CLIENT"
    SERVER = "SERVER"
    PRODUCER = "PRODUCER"
    CONSUMER = "CONSUMER"


class SchemaValidationError(ValueError):
    """Raised when a TraceEvent fails schema validation."""


# Operational-event statuses (Algorithm 1: start / complete / error)
OPERATIONAL_STATUSES = frozenset({"start", "complete", "error"})


@dataclass
class TraceEvent:
    """
    Unified trace-event envelope conforming to the AgentTrace schema.

    Every event across all three surfaces shares this common structure.
    The fields below realise the four schema properties of the paper:

      * consistency      — fixed envelope + ``validate()``
      * causality        — ``trace_id`` / ``span_id`` / ``parent_span_id`` /
                           ``timestamp``
      * fidelity         — surface-specific structured ``body``
      * interoperability — ``to_dict()`` (JSONL) and
                           ``to_otel_attributes()`` (OpenTelemetry)
    """

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    surface: TraceSurface = TraceSurface.OPERATIONAL
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    agent_name: str = ""
    level: TraceLevel = TraceLevel.INFO
    span_kind: SpanKind = SpanKind.INTERNAL
    body: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    # Validation (consistency property)

    def validate(self) -> None:
        """
        Validate the event against the AgentTrace schema.

        Raises ``SchemaValidationError`` if any required field is missing
        or malformed. ALogger invokes this at emission time, per
        AgentTrace §Implementation: "All records are validated at emission
        time against the schema to maintain consistency."
        """
        if not isinstance(self.surface, TraceSurface):
            raise SchemaValidationError(
                f"surface must be a TraceSurface, got {type(self.surface).__name__}"
            )
        if not isinstance(self.level, TraceLevel):
            raise SchemaValidationError(
                f"level must be a TraceLevel, got {type(self.level).__name__}"
            )
        if not isinstance(self.span_kind, SpanKind):
            raise SchemaValidationError(
                f"span_kind must be a SpanKind, got {type(self.span_kind).__name__}"
            )
        if not self.event_id:
            raise SchemaValidationError("event_id is required")
        if not self.trace_id or not _TRACE_ID_RE.match(self.trace_id):
            raise SchemaValidationError(
                f"trace_id must be 32 lowercase hex chars, got {self.trace_id!r}"
            )
        if not self.span_id or not _SPAN_ID_RE.match(self.span_id):
            raise SchemaValidationError(
                f"span_id must be 16 lowercase hex chars, got {self.span_id!r}"
            )
        if self.parent_span_id is not None and not _SPAN_ID_RE.match(self.parent_span_id):
            raise SchemaValidationError(
                f"parent_span_id must be 16 lowercase hex chars, got {self.parent_span_id!r}"
            )
        if not self.timestamp:
            raise SchemaValidationError("timestamp is required")
        if not isinstance(self.body, dict):
            raise SchemaValidationError("body must be a dict")

        # Surface-specific body requirements
        if self.surface == TraceSurface.OPERATIONAL:
            if "method" not in self.body or not self.body["method"]:
                raise SchemaValidationError(
                    "operational events require body.method"
                )
            status = self.body.get("status")
            if status not in OPERATIONAL_STATUSES:
                raise SchemaValidationError(
                    f"operational body.status must be one of "
                    f"{sorted(OPERATIONAL_STATUSES)}, got {status!r}"
                )
        elif self.surface == TraceSurface.COGNITIVE:
            # At least one cognitive payload field must be present
            if not any(
                    self.body.get(k)
                    for k in (
                            "thought", "plan", "reflection",
                            "prompt_summary", "completion_summary",
                    )
            ):
                raise SchemaValidationError(
                    "cognitive events require at least one of "
                    "thought/plan/reflection/prompt_summary/completion_summary"
                )
        elif self.surface == TraceSurface.CONTEXTUAL:
            if "operation" not in self.body or not self.body["operation"]:
                raise SchemaValidationError(
                    "contextual events require body.operation"
                )
            if "source" not in self.body or not self.body["source"]:
                raise SchemaValidationError(
                    "contextual events require body.source"
                )

    def is_valid(self) -> bool:
        """Return True iff ``validate()`` succeeds (never raises)."""
        try:
            self.validate()
            return True
        except SchemaValidationError:
            return False

    # Serialisation (interoperability property)

    def to_dict(self, omit_none: bool = False) -> Dict[str, Any]:
        """
        Serialize to a plain dict for JSON / OTel export.

        Args:
            omit_none: When True, fields whose value is ``None`` are
                dropped. This produces leaner JSONL records without
                losing schema compatibility (consumers should treat
                missing keys as ``None``).
        """
        d: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "surface": self.surface.value,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "timestamp": self.timestamp,
            "agent_name": self.agent_name,
            "level": self.level.value,
            "span_kind": self.span_kind.value,
            "body": self.body,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "tags": self.tags,
        }
        if omit_none:
            d = {k: v for k, v in d.items() if v is not None}
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "TraceEvent":
        """Deserialize from a plain dict (e.g. a JSONL line)."""
        return cls(
            event_id=d.get("event_id", uuid.uuid4().hex),
            surface=TraceSurface(d.get("surface", "operational")),
            trace_id=d.get("trace_id", ""),
            span_id=d.get("span_id", ""),
            parent_span_id=d.get("parent_span_id"),
            timestamp=d.get("timestamp", ""),
            agent_name=d.get("agent_name", ""),
            level=TraceLevel(d.get("level", "INFO")),
            span_kind=SpanKind(d.get("span_kind", "INTERNAL")),
            body=dict(d.get("body", {})),
            duration_ms=d.get("duration_ms"),
            error=d.get("error"),
            tags=dict(d.get("tags", {})),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )

    def to_otel_attributes(self) -> Dict[str, Any]:
        """
        Produce a flat ``{key: scalar}`` attribute mapping suitable for
        ``Span.set_attributes`` / ``start_span(attributes=...)``.

        Centralising this mapping here (rather than in otel_exporter.py)
        keeps the schema authoritative and ensures every surface uses
        consistent attribute namespacing across both the JSONL and OTel
        backends — the interoperability property of the schema.

        Naming follows OpenTelemetry semantic conventions where possible:
          * ``http.*``  for HTTP I/O
          * ``db.*``    for SQL / database I/O
          * ``cache.*`` for cache stores
          * ``vector.*`` for vector DBs
          * ``llm.*``   for LLM cognitive events
          * ``agent.*`` for agent-level metadata
          * ``body.*``  for anything else from the body payload
        """
        attrs: Dict[str, Any] = {
            "agent.name": self.agent_name,
            "agent.event_id": self.event_id,
            "agent.surface": self.surface.value,
            "agent.level": self.level.value,
            "agent.schema_version": self.schema_version,
        }
        if self.duration_ms is not None:
            attrs["agent.duration_ms"] = self.duration_ms
        if self.error:
            attrs["agent.error"] = self.error

        body = self.body or {}

        if self.surface == TraceSurface.OPERATIONAL:
            for src, dst in (
                    ("method", "agent.method"),
                    ("status", "agent.status"),
                    ("args_summary", "agent.args_summary"),
                    ("args_count", "agent.args_count"),
                    ("result_summary", "agent.result_summary"),
                    ("result_type", "agent.result_type"),
                    ("duration_ms", "agent.duration_ms"),
            ):
                if body.get(src) is not None:
                    attrs[dst] = body[src]

        elif self.surface == TraceSurface.COGNITIVE:
            for src, dst in (
                    ("model", "llm.model"),
                    ("temperature", "llm.temperature"),
                    ("prompt_tokens", "llm.prompt_tokens"),
                    ("completion_tokens", "llm.completion_tokens"),
                    ("total_tokens", "llm.total_tokens"),
                    ("prompt_summary", "llm.prompt_summary"),
                    ("completion_summary", "llm.completion_summary"),
                    ("thought", "llm.thought"),
                    ("plan", "llm.plan"),
                    ("reflection", "llm.reflection"),
                    ("confidence", "llm.confidence"),
                    ("extraction_method", "llm.extraction_method"),
            ):
                if body.get(src) is not None:
                    attrs[dst] = body[src]

        elif self.surface == TraceSurface.CONTEXTUAL:
            op = body.get("operation", "")
            src = body.get("source", "")
            attrs["io.operation"] = op
            attrs["io.source"] = src

            # HTTP semantic conventions
            for k, dst in (
                    ("url", "http.url"),
                    ("http_method", "http.method"),
                    ("status_code", "http.status_code"),
                    ("headers_summary", "http.headers_summary"),
                    ("latency_ms", "http.latency_ms"),
            ):
                if body.get(k) is not None:
                    attrs[dst] = body[k]

            # SQL / DB semantic conventions
            for k, dst in (
                    ("query_summary", "db.statement"),
                    ("row_count", "db.row_count"),
                    ("db_system", "db.system"),
            ):
                if body.get(k) is not None:
                    attrs[dst] = body[k]

            # Cache / vector store semantic conventions
            for k, dst in (
                    ("cache_key", "cache.key"),
                    ("cache_hit", "cache.hit"),
                    ("vector_query", "vector.query_summary"),
                    ("vector_top_k", "vector.top_k"),
            ):
                if body.get(k) is not None:
                    attrs[dst] = body[k]

            for k, dst in (
                    ("response_summary", "io.response_summary"),
                    ("byte_count", "io.byte_count"),
            ):
                if body.get(k) is not None:
                    attrs[dst] = body[k]

        # Anything left in body that we did not map explicitly is exposed
        # under body.* for full fidelity (paper §Methodology: fidelity).
        _mapped: Iterable[str] = {
            # operational
            "method", "status", "args_summary", "args_count",
            "result_summary", "result_type", "duration_ms",
            # cognitive
            "model", "temperature",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "prompt_summary", "completion_summary",
            "thought", "plan", "reflection",
            "confidence", "extraction_method",
            # contextual
            "operation", "source",
            "url", "http_method", "status_code",
            "headers_summary", "latency_ms",
            "query_summary", "row_count", "db_system",
            "cache_key", "cache_hit",
            "vector_query", "vector_top_k",
            "response_summary", "byte_count",
        }
        for k, v in body.items():
            if k in _mapped or v is None:
                continue
            attrs[f"body.{k}"] = v

        # User-supplied tags (preserved verbatim)
        for k, v in (self.tags or {}).items():
            attrs[f"tag.{k}"] = v

        return attrs

    # Convenience

    @property
    def is_error(self) -> bool:
        """Check whether this event represents an error."""
        return self.level == TraceLevel.ERROR or self.error is not None

    @property
    def timestamp_ns(self) -> Optional[int]:
        """
        Parse ``timestamp`` (ISO-8601 UTC) and return Unix-epoch nanoseconds,
        or ``None`` if the timestamp is unparseable. Used by the OTel exporter
        to back-date spans so Jaeger / Tempo display them at event time
        rather than at export time.
        """
        if not self.timestamp:
            return None
        try:
            ts = self.timestamp
            # datetime.fromisoformat accepts "+00:00" but not "Z"; normalise.
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1_000_000_000)
        except (ValueError, TypeError):
            return None


# Surface body builders
#
# Each builder returns a ``Dict[str, Any]`` that ALogger embeds as
# ``TraceEvent.body``. Builders are tolerant of None values (they are
# omitted) and forward unknown kwargs via ``**extra`` so callers can attach
# bespoke metadata without modifying the schema.


def _populate(body: Dict[str, Any], **fields) -> Dict[str, Any]:
    """Insert any non-None field into ``body`` and return it."""
    for k, v in fields.items():
        if v is not None:
            body[k] = v
    return body


def make_operational_body(
        method: str,
        status: str,
        args_summary: Optional[str] = None,
        args_count: Optional[int] = None,
        result_summary: Optional[str] = None,
        result_type: Optional[str] = None,
        duration_ms: Optional[float] = None,
        **extra,
) -> Dict[str, Any]:
    """
    Build an operational surface event body.

    Per AgentTrace §Operational Surface: "Each method invocation produces a
    pair of events — start and complete — enriched with span-level metadata
    such as argument count, result type, and execution duration."
    """
    if status not in OPERATIONAL_STATUSES:
        raise SchemaValidationError(
            f"operational status must be one of {sorted(OPERATIONAL_STATUSES)}, "
            f"got {status!r}"
        )
    body: Dict[str, Any] = {"method": method, "status": status}
    _populate(
        body,
        args_summary=args_summary,
        args_count=args_count,
        result_summary=result_summary,
        result_type=result_type,
        duration_ms=duration_ms,
    )
    body.update(extra)
    return body


def make_cognitive_body(
        thought: Optional[str] = None,
        plan: Optional[str] = None,
        reflection: Optional[str] = None,
        model: Optional[str] = None,
        prompt_summary: Optional[str] = None,
        completion_summary: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        confidence: Optional[float] = None,
        **extra,
) -> Dict[str, Any]:
    """
    Build a cognitive surface event body.

    Per AgentTrace §Cognitive Surface, this captures raw prompts, completions,
    extracted reasoning chains (CoT), and confidence estimates.
    """
    body: Dict[str, Any] = {}
    _populate(
        body,
        thought=thought,
        plan=plan,
        reflection=reflection,
        model=model,
        prompt_summary=prompt_summary,
        completion_summary=completion_summary,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        temperature=temperature,
        confidence=confidence,
    )
    body.update(extra)
    return body


def make_contextual_body(
        operation: str,
        source: str,
        query_summary: Optional[str] = None,
        response_summary: Optional[str] = None,
        byte_count: Optional[int] = None,
        row_count: Optional[int] = None,
        status_code: Optional[int] = None,
        # HTTP-specific
        url: Optional[str] = None,
        http_method: Optional[str] = None,
        headers_summary: Optional[str] = None,
        latency_ms: Optional[float] = None,
        # DB-specific
        db_system: Optional[str] = None,
        # Cache / vector-store specific
        cache_key: Optional[str] = None,
        cache_hit: Optional[bool] = None,
        vector_query: Optional[str] = None,
        vector_top_k: Optional[int] = None,
        **extra,
) -> Dict[str, Any]:
    """
    Build a contextual surface event body (external I/O).

    Per AgentTrace §Contextual Surface: "Each contextual interaction produces
    a span enriched with resource-specific metadata: URLs and headers for HTTP,
    query structure and row counts for SQL, and key/value operations for cache
    or vector DBs."

    All resource-specific fields are optional; pass whatever is relevant to
    the operation being logged.
    """
    body: Dict[str, Any] = {"operation": operation, "source": source}
    _populate(
        body,
        query_summary=query_summary,
        response_summary=response_summary,
        byte_count=byte_count,
        row_count=row_count,
        status_code=status_code,
        url=url,
        http_method=http_method,
        headers_summary=headers_summary,
        latency_ms=latency_ms,
        db_system=db_system,
        cache_key=cache_key,
        cache_hit=cache_hit,
        vector_query=vector_query,
        vector_top_k=vector_top_k,
    )
    body.update(extra)
    return body
