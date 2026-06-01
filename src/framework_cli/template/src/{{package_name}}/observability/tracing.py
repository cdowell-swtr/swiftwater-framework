"""OpenTelemetry tracing setup.

Off unless settings.otel_enabled (the dev Compose app sets APP_OTEL_ENABLED=true). When on,
auto-instruments FastAPI and exports spans via OTLP/gRPC to the OTEL Collector, which forwards
them to Tempo. The OTel SDK/exporter/instrumentation are imported lazily here so a disabled app
(tests, lite, local uvicorn) never imports them or starts an exporter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.trace import TracerProvider

    from ..config.settings import Settings


def _build_tracer_provider(settings: "Settings") -> "TracerProvider":
    """Build + register a TracerProvider exporting spans via OTLP/gRPC.

    Shared by the FastAPI (app) and Celery (worker) tracing setups. OTel imports are
    local so a disabled process never imports the SDK or starts an exporter.
    """
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint, insecure=True
            )
        )
    )
    trace.set_tracer_provider(provider)
    return provider


def configure_tracing(app: "FastAPI", settings: "Settings") -> None:
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _build_tracer_provider(settings)
    FastAPIInstrumentor.instrument_app(app)


def configure_worker_tracing(settings: "Settings") -> None:
    """Initialize tracing for a Celery worker process (call from worker_process_init).

    Builds the shared provider and instruments Celery so task executions are traced and
    the trace context from the enqueuing request is continued. No-op when OTel is off.
    """
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    _build_tracer_provider(settings)
    CeleryInstrumentor().instrument()
