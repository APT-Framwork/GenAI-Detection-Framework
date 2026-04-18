"""OpenTelemetry tracing scaffolding (§8.3 + P8-4).

Disabled by default; turns on when `OBS_TRACING_ENABLED=true` and
`OBS_OTLP_ENDPOINT` is set. Falls back to a no-op tracer so call sites
can use `traced("span_name")` without checking flags.

Span boundaries (§8.3):
  api.{route}              per HTTP request (auto via FastAPIInstrumentor)
  pipeline.normalizer      child: parse, secbert, pca, scale
  pipeline.inference       child: ae, vae, transformer, gnn, state_builder, dqn
  db.{operation}           per DB query (manual)
  redis.{cmd}              per Redis op  (manual)
  http.{adapter}           per upstream call (manual; via httpx instrumentation)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from strix_api.observability import get_logger
from strix_api.settings import ObservabilitySettings

log = get_logger("strix_api.observability.tracing")

_TRACER: Any = None


def configure_tracing(
    *,
    settings: ObservabilitySettings,
    service_name: str,
) -> None:
    """Idempotent OTLP setup. No-op when tracing disabled or endpoint missing."""
    global _TRACER
    if not settings.tracing_enabled or not settings.otlp_endpoint:
        log.debug("tracing_disabled", enabled=settings.tracing_enabled)
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        log.warning("tracing_skipped_missing_otel_packages", exc_info=exc)
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{settings.otlp_endpoint.rstrip('/')}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer("strix_api")
    log.info(
        "tracing_enabled",
        service=service_name,
        otlp_endpoint=settings.otlp_endpoint,
    )


def instrument_fastapi(app: Any) -> None:
    """Wire the FastAPI request → span instrumentation. Safe when OTel absent."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        return
    if _TRACER is None:
        return
    FastAPIInstrumentor.instrument_app(app)


@contextmanager
def traced(name: str, **attrs: Any) -> Iterator[Any]:
    """Context manager — opens a span when tracing is on, no-op otherwise.

    Usage:
        with traced("pipeline.ae", batch_size=len(items)):
            ...
    """
    if _TRACER is None:
        yield None
        return
    with _TRACER.start_as_current_span(name) as span:
        for k, v in attrs.items():
            span.set_attribute(k, v)
        yield span


__all__ = ["configure_tracing", "instrument_fastapi", "traced"]
