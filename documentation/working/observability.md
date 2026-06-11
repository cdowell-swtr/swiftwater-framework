# Observability

Every scaffolded project is observable from the first line of code. Metrics, structured logs, and distributed traces are wired in for you, and the same observability stack runs in dev, CI, staging, and production — so the dashboard you watch locally is the dashboard you watch in production. You don't bolt observability on later; it's already there.

This page explains the model: how traces, logs, and metrics are produced, and what runs them.

## Tracing is automatic — no manual spans

Tracing uses [OpenTelemetry](https://opentelemetry.io) **auto-instrumentation**. Your application code carries no manual spans and makes no tracing calls. When tracing is enabled, the framework instruments the libraries your code already uses:

- `FastAPIInstrumentor` instruments the web layer, so every request produces a span.
- `SQLAlchemyInstrumentor` instruments the database, so every query produces a child span that continues the request's trace.

(Battery data stores extend the same auto-instrumentation — e.g. Redis or MongoDB get instrumented the same way when those batteries are present.) Setup lives in `observability/tracing.py` and `observability/datastores.py`. Spans are exported over OTLP/gRPC to the OpenTelemetry Collector, which forwards traces to Tempo, viewable in Grafana.

Tracing is **off by default** and turns on via the `APP_OTEL_ENABLED` setting (with `APP_OTEL_EXPORTER_OTLP_ENDPOINT` pointing at the collector). The `dev` Compose stack sets these for you, so traces flow as soon as you `task dev`. A process with tracing off never even imports the OTel SDK — the imports are lazy — so tests and `dev:lite` pay nothing for it.

## Logs are structured, with correlation and trace context auto-injected

Logging uses [structlog](https://www.structlog.org). You log through the project's logger and pass fields as keyword arguments:

```python
from your_package.logging_config import get_logger

log = get_logger()
log.info("order_placed", order_id=order.id, total_cents=total)
```

Logs render as JSON, and three things are attached to every entry **automatically**, without you doing anything:

- **`correlation_id`** — generated at every request boundary by the observability middleware (or taken from an inbound `X-Correlation-ID` header) and stored in a contextvar. The `add_correlation_id` structlog processor injects it into every log entry emitted within that request's async context, so all logs for one request share an id. The id is also echoed back on the response's `X-Correlation-ID` header.
- **`trace_id` / `span_id`** — when a trace is active, the `add_trace_context` processor injects the current OpenTelemetry trace and span ids, so a log line ties directly to its trace.
- **log level** — environment-aware: `DEBUG` locally, `INFO` everywhere else (resolved from `APP_ENVIRONMENT` unless you set `APP_LOG_LEVEL` explicitly).

Because correlation and trace context are injected at the logger, you get request-scoped, trace-linked logs for free — just call `get_logger().info(...)`.

## Metrics, SLOs, and the `/health` report

Request latency and status are recorded by the observability middleware into an in-process metrics registry. Two endpoints read it:

- **`/metrics`** — Prometheus text exposition (raw counters, gauges, histograms). Scraped by Prometheus.
- **`/health`** — a structured readiness report that evaluates the project's SLOs against current values.

SLOs live in code as typed configuration in `observability/slo.py` — a single source of truth. The same definitions drive the `/health` evaluation **and** the auto-generated Grafana dashboards and Prometheus alert rules (`observability/provisioning.py` turns the SLOs into PromQL; `task observability:gen` regenerates the rules and dashboard into `infra/observability/`). Adding or changing an SLO updates the health check, the dashboard, and the alerts together — they can't drift apart.

The project also tracks **recoverability** metrics (retries scheduled, recoveries, exhaustions, and circuit-breaker state) so the resilience layer is observable too. The monitoring endpoints themselves (`/health`, `/metrics`, `/heartbeat`) are excluded from request metrics, so monitoring traffic doesn't skew the SLOs.

## The stack that runs it

When the observability overlay (`infra/compose/observability.yml`) is active, the project runs a full stack:

| Component | Role |
|---|---|
| Prometheus | Scrapes `/metrics` from the app (and the exporters); stores metrics; evaluates alert rules |
| Grafana | Dashboards (auto-provisioned from the SLOs); a unified view over metrics, logs, and traces |
| Alertmanager | Routes fired alerts (e.g. an SLO breach) to a webhook receiver |
| Loki | Structured log aggregation |
| Promtail | Ships container logs into Loki |
| Tempo | Distributed trace storage; traces are viewable in Grafana with trace-to-log correlation |
| OpenTelemetry Collector | Receives spans over OTLP/gRPC and exports them to Tempo |

A `postgres-exporter` exposes database metrics to Prometheus; batteries add their own exporters when present (e.g. a Redis or Celery exporter).

## The same stack everywhere — including locally

The observability overlay is merged into dev, staging, and production — the stack is defined once and runs identically in each. This is deliberate: there is no separate "production-only" monitoring you can't see while developing. You watch the real dashboard, fire the real alerts, and read the real traces on your own machine. The one exception is `task dev:lite`, which opts out of the overlay to stay resource-light — use the full `task dev` when you want the observability stack up.

This parity is the whole point: because the obs stack is the same definition across environments, what you verify locally is what runs in production — there's no observability gap to discover after you ship.
