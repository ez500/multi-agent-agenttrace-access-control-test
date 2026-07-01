"""
otel_exporter.py — OpenTelemetry Export Bridge for AgentTrace

Converts ``TraceEvent`` objects into OpenTelemetry spans and exports them
through an OTel batch span processor. Per AgentTrace §Implementation:

  "When enabled, AgentTrace converts each event into an OTel span and
   exports via a batch processor. ... Exporter failures gracefully degrade
   to local JSONL."

Key design choices implemented here:

  * Schema-driven attributes — surface-specific attribute namespacing is
    owned by ``TraceEvent.to_otel_attributes`` in trace_schema.py, so this
    file stays small and the schema remains authoritative.

  * Causal nesting — every AgentTrace span carries the framework's own
    ``trace_id`` / ``span_id`` / ``parent_span_id``. We honour those by
    constructing a ``NonRecordingSpan`` with a synthetic ``SpanContext``
    so the emitted OTel span participates in the *same* trace tree as its
    parent. Without this, Jaeger / Tempo would show one orphan root span
    per event and the §Methodology guarantee — "Span nesting and context
    propagation enforce temporal causality across reasoning, tool, and
    workflow events" — would be lost.

  * Event-time spans — exports use the event's own UTC timestamp via
    ``timestamp_ns`` so the backend visualises spans at the time the event
    actually happened, not at export time. Duration (when known) is
    applied to ``end_time`` accordingly.

  * Transport flexibility — OTLP/gRPC (default) with automatic fallback to
    OTLP/HTTP when the gRPC exporter is unavailable, and a console
    exporter for offline development. Endpoint inference also honours the
    ``OTEL_EXPORTER_OTLP_ENDPOINT`` environment variable for
    interoperability with standard OTel deployments.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from trace_schema import SpanKind, TraceEvent, TraceSurface

logger = logging.getLogger(__name__)


# Lazy OpenTelemetry imports (optional dependency)

_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        SimpleSpanProcessor,
        ConsoleSpanExporter,
        SpanExporter,
        SpanExportResult,
    )
    from opentelemetry.trace import (
        Link,
        NonRecordingSpan,
        SpanContext,
        SpanKind as OTelSpanKind,
        TraceFlags,
        set_span_in_context,
    )
    from opentelemetry.trace.status import Status, StatusCode

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when OTel is absent
    otel_trace = None  # type: ignore
    Resource = None  # type: ignore
    TracerProvider = None  # type: ignore
    BatchSpanProcessor = None  # type: ignore
    SimpleSpanProcessor = None  # type: ignore
    ConsoleSpanExporter = None  # type: ignore
    Link = None  # type: ignore
    NonRecordingSpan = None  # type: ignore
    SpanContext = None  # type: ignore
    OTelSpanKind = None  # type: ignore
    TraceFlags = None  # type: ignore
    set_span_in_context = None  # type: ignore
    Status = None  # type: ignore
    StatusCode = None  # type: ignore


# Helpers

def _span_name_from_event(event: TraceEvent) -> str:
    """Derive a human-readable span name from a trace event."""
    agent = event.agent_name or "agent"
    if event.surface == TraceSurface.OPERATIONAL:
        method = event.body.get("method", "unknown")
        status = event.body.get("status", "")
        return f"{agent}.{method}.{status}" if status else f"{agent}.{method}"
    if event.surface == TraceSurface.COGNITIVE:
        model = event.body.get("model")
        return f"{agent}.llm.{model}" if model else f"{agent}.llm"
    if event.surface == TraceSurface.CONTEXTUAL:
        op = event.body.get("operation", "io")
        source = event.body.get("source", "unknown")
        return f"{agent}.{op}.{source}"
    return f"{agent}.event"


def _otel_span_kind(kind: SpanKind):
    """Map AgentTrace ``SpanKind`` → OTel ``SpanKind``."""
    if OTelSpanKind is None:
        return None
    return {
        SpanKind.INTERNAL: OTelSpanKind.INTERNAL,
        SpanKind.CLIENT: OTelSpanKind.CLIENT,
        SpanKind.SERVER: OTelSpanKind.SERVER,
        SpanKind.PRODUCER: OTelSpanKind.PRODUCER,
        SpanKind.CONSUMER: OTelSpanKind.CONSUMER,
    }.get(kind, OTelSpanKind.INTERNAL)


def _hex_to_int(value: str, width: int) -> Optional[int]:
    """Parse ``value`` as a hex int of exactly ``width`` chars; return None on failure."""
    if not value or len(value) != width:
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


def _otel_value(value: Any) -> Any:
    """Coerce ``value`` into something OTel ``set_attribute`` accepts."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        if all(isinstance(x, (str, int, float, bool)) for x in value):
            return list(value)
        return [str(x) for x in value]
    return str(value)


# JSONL Span Exporter


def _make_jsonl_span_exporter(jsonl_path: Path):
    """
    Build a SpanExporter that writes every OTel span (operational, cognitive,
    contextual — including auto-instrumented httpx / sqlite3 / requests / etc.)
    as a JSON line to ``jsonl_path``.

    Why this exists: AgentTrace's auto-instrumented contextual spans (HTTP,
    SQL) are emitted *directly* into the OTel tracer pipeline by the OTel
    instrumentation libraries — they never flow through ``ALogger.record_*``,
    so ``mirror_contextual_to_jsonl`` doesn't see them. To keep "everything
    on disk" working for offline review of the JSONL, attach a second span
    processor that taps the same OTel stream and mirrors spans to JSONL in
    a schema close to ``TraceEvent.to_dict()``.

    Spans emitted via ``OTelExporter.export_event`` are skipped here by
    detecting the ``agenttrace.surface`` attribute we always set — those
    are already written to JSONL by ALogger, so re-mirroring would double-
    count.
    """
    if not _OTEL_AVAILABLE or SpanExporter is None:
        return None

    class _JsonlSpanExporter(SpanExporter):  # type: ignore[misc]
        def __init__(self, path: Path):
            self._path = path
            self._path.parent.mkdir(parents=True, exist_ok=True)

        def export(self, spans):  # type: ignore[override]
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    for span in spans:
                        ctx = span.get_span_context()
                        attrs = dict(span.attributes or {})
                        # Avoid double-write for spans that already came from
                        # AgentTrace's own ALogger pipeline; ALogger has
                        # already persisted them as TraceEvent records. The
                        # schema namespaces these attributes under `agent.*`
                        # (see trace_schema.to_otel_attributes), so detect by
                        # `agent.surface` (or `agent.event_id`, defensively).
                        if "agent.surface" in attrs or "agent.event_id" in attrs:
                            continue
                        record = {
                            "schema_version": "1.1",
                            # This processor only writes spans that did NOT
                            # come from ALogger (the filter above), so by
                            # definition these are auto-instrumented
                            # contextual spans (httpx, sqlite3, requests, …).
                            "surface": "contextual",
                            "trace_id": f"{ctx.trace_id:032x}",
                            "span_id": f"{ctx.span_id:016x}",
                            "parent_span_id": (
                                f"{span.parent.span_id:016x}" if span.parent else None
                            ),
                            "name": span.name,
                            "kind": str(span.kind),
                            "start_time_ns": span.start_time,
                            "end_time_ns": span.end_time,
                            "duration_ns": (
                                (span.end_time - span.start_time)
                                if (span.start_time and span.end_time)
                                else None
                            ),
                            "status": str(span.status.status_code)
                            if getattr(span, "status", None)
                            else None,
                            "instrumentation": (
                                span.instrumentation_scope.name
                                if getattr(span, "instrumentation_scope", None)
                                else None
                            ),
                            "attributes": {k: v for k, v in attrs.items()},
                        }
                        f.write(json.dumps(record, default=str) + "\n")
            except Exception as e:  # pragma: no cover — defensive: never crash
                logger.debug(f"JSONL span mirror failed (non-critical): {e}")
                return SpanExportResult.FAILURE  # type: ignore[union-attr]
            return SpanExportResult.SUCCESS  # type: ignore[union-attr]

        def shutdown(self):  # type: ignore[override]
            return None

        def force_flush(self, timeout_millis: int = 30000):  # type: ignore[override]
            return True

    return _JsonlSpanExporter(jsonl_path)


# OTel Span Exporter

class OTelExporter:
    """
    Converts AgentTrace ``TraceEvent`` records to OpenTelemetry spans and
    exports them through a (batch) span processor.

    Graceful degradation: if OTel is not installed, the constructor or
    transport fails, or a single export call raises, methods become
    no-ops and ALogger falls back to JSONL (per AgentTrace §Implementation).
    """

    def __init__(
            self,
            service_name: str = "AgentTrace_logging",
            endpoint: Optional[str] = None,
            use_batch: bool = True,
            resource_attributes: Optional[Dict[str, str]] = None,
            jsonl_mirror_path: Optional[Path] = None,
    ):
        self._tracer = None
        self._provider = None
        self._processor = None
        self._enabled = False
        self._service_name = service_name

        if not _OTEL_AVAILABLE:
            logger.info("OpenTelemetry not installed — OTel export disabled")
            return

        try:
            # Resource — service.name + optional supplemental attributes
            attrs: Dict[str, str] = {"service.name": service_name}
            if resource_attributes:
                attrs.update(resource_attributes)
            resource = Resource.create(attrs)  # type: ignore[union-attr]
            self._provider = TracerProvider(resource=resource)  # type: ignore[misc]

            # Exporter — OTLP/gRPC → OTLP/HTTP → Console
            endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
            span_exporter, transport = self._build_exporter(endpoint)
            if span_exporter is None:
                return

            # Processor
            processor_cls = (
                BatchSpanProcessor if use_batch and BatchSpanProcessor is not None
                else SimpleSpanProcessor
            )
            if processor_cls is None:
                return
            self._processor = processor_cls(span_exporter)
            self._provider.add_span_processor(self._processor)

            # Second span processor — mirrors every OTel span (including the
            # auto-instrumented contextual ones for httpx / sqlite3 / etc.)
            # to a JSONL file. Without this the contextual surface is
            # invisible offline because the auto-instrumentors bypass
            # ALogger entirely. Skipped if no path was provided.
            if jsonl_mirror_path is not None:
                jsonl_exporter = _make_jsonl_span_exporter(jsonl_mirror_path)
                if jsonl_exporter is not None:
                    self._provider.add_span_processor(
                        SimpleSpanProcessor(jsonl_exporter)  # type: ignore[misc]
                    )

            # Install provider only if a global one has not already been set
            # (avoid clobbering an embedding application's tracer provider).
            current = otel_trace.get_tracer_provider()  # type: ignore[union-attr]
            if not isinstance(current, TracerProvider):  # type: ignore[arg-type]
                otel_trace.set_tracer_provider(self._provider)  # type: ignore[union-attr]
                self._tracer = self._provider.get_tracer(service_name)
            else:
                # Reuse the existing provider's tracer so we participate in
                # the host application's trace pipeline.
                self._tracer = current.get_tracer(service_name)

            self._enabled = self._tracer is not None
            logger.info(
                f"OTel exporter initialized "
                f"(service={service_name}, transport={transport})"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize OTel exporter: {e}")
            self._enabled = False

    # Transport selection

    @staticmethod
    def _build_exporter(endpoint: Optional[str]) -> Tuple[Any, str]:
        """
        Construct an OTLP span exporter, with graceful fallbacks:

          1. OTLP/gRPC (if endpoint provided and grpc exporter available)
          2. OTLP/HTTP (fallback when gRPC isn't installed)
          3. ConsoleSpanExporter (for offline development)

        Returns (exporter, transport_label).
        """
        if endpoint:
            # Plain-HTTP endpoints (e.g. `http://jaeger:4317`) need
            # insecure=True on the gRPC exporter or the OTLP client will
            # try TLS and fail with "CANCELLED" / handshake errors. We
            # detect this from the scheme; an https:// endpoint or a
            # bare host:port goes through with TLS defaults.
            insecure = endpoint.startswith("http://")
            # Route OTLP/HTTP endpoints (4318 / `/v1/traces`) straight to
            # the HTTP exporter instead of the gRPC one — gRPC on 4318
            # would silently fail.
            looks_http = ":4318" in endpoint or endpoint.rstrip("/").endswith("/v1/traces")
            if not looks_http:
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                        OTLPSpanExporter as GRPCExporter,
                    )
                    return (
                        GRPCExporter(endpoint=endpoint, insecure=insecure),
                        f"otlp-grpc:{endpoint}",
                    )
                except Exception as e:
                    logger.debug(f"OTLP/gRPC unavailable ({e}); trying OTLP/HTTP")
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter as HTTPExporter,
                )
                return HTTPExporter(endpoint=endpoint), f"otlp-http:{endpoint}"
            except Exception as e:
                logger.debug(f"OTLP/HTTP unavailable ({e}); falling back to console")


        # Final fallback — console exporter for local development
        if ConsoleSpanExporter is None:
            return None, "none"
        return ConsoleSpanExporter(), "console"

    @property
    def enabled(self) -> bool:
        """Check whether OTel export is available and configured."""
        return self._enabled

    # Causal context propagation

    def _parent_context(self, event: TraceEvent):
        """
        Build an OTel ``Context`` that anchors the new span as a child of
        the AgentTrace ``parent_span_id`` (or, if absent, as a root in the
        same ``trace_id``). This is what realises the paper's claim of
        nested causal spans across operational / cognitive / contextual
        surfaces.
        """
        if NonRecordingSpan is None or SpanContext is None or set_span_in_context is None:
            return None
        # Don't self-parent: if the event has no parent, it's a root —
        # let OTel start a new root span context rather than referencing
        # a span_id that doesn't (yet) exist. Self-parenting was the
        # source of Jaeger's "invalid parent span IDs ... skipping clock
        # skew adjustment" warnings on every root event.
        if not event.parent_span_id:
            return None
        trace_id_int = _hex_to_int(event.trace_id, 32)
        span_id_int = _hex_to_int(event.parent_span_id, 16)
        if trace_id_int is None or span_id_int is None:
            return None

        try:
            ctx = SpanContext(
                trace_id=trace_id_int,
                span_id=span_id_int,
                is_remote=False,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),  # type: ignore[arg-type]
            )
            return set_span_in_context(NonRecordingSpan(ctx))
        except Exception as e:
            logger.debug(f"Failed to build parent context: {e}")
            return None

    # Export

    def export_event(self, event: TraceEvent) -> bool:
        """
        Export a single ``TraceEvent`` as an OTel span. Returns ``True``
        on success; ``False`` lets the caller fall back to JSONL.
        """
        if not self._enabled or self._tracer is None:
            return False

        try:
            span_name = _span_name_from_event(event)
            otel_kind = _otel_span_kind(event.span_kind)
            if otel_kind is None:
                return False

            # Causal anchoring: child of parent_span_id (if any) within trace_id.
            parent_context = self._parent_context(event)

            # Use the event's UTC timestamp so backends show the span at the
            # time it actually happened, not at export time.
            start_ns = event.timestamp_ns
            end_ns: Optional[int] = None
            if start_ns is not None and event.duration_ms is not None:
                end_ns = start_ns + int(event.duration_ms * 1_000_000)

            attributes = event.to_otel_attributes()
            # Coerce values defensively (OTel attribute API rejects arbitrary types).
            safe_attrs = {k: _otel_value(v) for k, v in attributes.items() if v is not None}

            span = self._tracer.start_span(
                name=span_name,
                context=parent_context,
                kind=otel_kind,
                attributes=safe_attrs,
                start_time=start_ns,
            )

            # Error semantics
            if event.is_error and Status is not None and StatusCode is not None:
                span.set_status(Status(StatusCode.ERROR, event.error or "unknown error"))
                if event.error:
                    try:
                        span.record_exception(Exception(event.error))
                    except Exception:
                        pass

            span.end(end_time=end_ns)
            return True
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Failed to export OTel span: {e}")
            return False

    def export_events(self, events: List[TraceEvent]) -> int:
        """Export multiple ``TraceEvent``s; return success count."""
        count = 0
        for event in events:
            if self.export_event(event):
                count += 1
        return count

    # Lifecycle

    def shutdown(self) -> None:
        """Shutdown the OTel exporter gracefully (flushes pending spans)."""
        if self._provider is not None:
            try:
                self._provider.shutdown()
            except Exception:  # pragma: no cover - defensive
                pass

    def force_flush(self, timeout_millis: int = 5000) -> bool:
        """Force flush any pending spans. Returns False on failure / no provider."""
        if self._provider is None:
            return False
        try:
            return bool(self._provider.force_flush(timeout_millis))
        except Exception:  # pragma: no cover - defensive
            return False
