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

    from ..config.settings import Settings


def configure_tracing(app: "FastAPI", settings: "Settings") -> None:
    if not settings.otel_enabled:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
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
    FastAPIInstrumentor.instrument_app(app)
