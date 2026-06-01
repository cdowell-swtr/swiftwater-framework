# Observability-infra self-monitoring + completeness guard — design

**Date:** 2026-06-01
**Status:** approved (brainstorm) → ready for implementation plan
**Source findings:** template-audit `template-audit-2026-05-31-76d9b65` (observability-infra, 2× high) — *"otel-collector is deployed but has no Prometheus scrape job"* and *"the prometheus self-scrape job has no alert rule."* Implements the `CLAUDE.md` known follow-up: a framework check that *"a battery/service that adds a compose service or external store but no scrape target + alert + dashboard"* fails. obs-completeness **sub-slice B** (sub-slice A = data-store trace instrumentation, merged `806ecc5`; sub-slice C = `_latencies_ms` cap + GraphQL introspection logging, follows).

## Problem

The generated obs stack monitors the app and every data-store exporter, but **does not monitor two of its own base components**:

- **otel-collector** is deployed (base obs stack, `infra/compose/observability.yml`) but has **no Prometheus scrape job**, **no alert**, and its config (`infra/observability/otel/otel-collector.yml`) has **no `service.telemetry` section** — so its internal Prometheus metrics aren't even exposed on the container network (the collector's default `:8888` binds to localhost inside the container). A collector crash/backpressure is invisible.
- **prometheus** self-scrapes (`job_name: prometheus` exists in `prometheus.yml`) but has **no alert rule** and **no dashboard** — a config-reload failure or self-scrape gap is unsignalled.

Every *data-store exporter* (postgres base; mongodb/celery/redis battery-gated) already has the full trio — a scrape job, an `<x>_alerts.yml` with `up{job="<x>"}==0`, and a dashboard referencing `job="<x>"`. The two base infra components are the only gaps. There is also no **framework-side guard** to stop a future exporter-adding battery from regressing the same way (the gap was caught by a human/audit, not a test).

Verified invariant (current template): jobs `postgres`/`celery`/`mongodb`/`redis` each have an alert referencing `up{job="…"}` and a dashboard referencing `job="…"`. Jobs `prometheus` (no alert/dashboard) and `otel-collector` (no scrape job at all) are the gaps. The `app` job is the application itself (SLO dashboards/alerts — a different model) and is excluded from the guard.

## Scope

**In scope**
1. otel-collector self-monitoring: expose its `:8888` metrics, scrape them, alert on down, dashboard.
2. prometheus self-monitoring: alert (down + config-reload-failed) + dashboard. (Self-scrape job already exists.)
3. A framework completeness-guard test enforcing scrape + alert + dashboard for every infra/exporter Prometheus job.

**Out of scope**
- `_latencies_ms` cap + GraphQL introspection logging — **sub-slice C**.
- Alertmanager routing/receivers changes.
- The `app` SLO dashboards/alerts (different model; `app` job excluded from the guard).
- Centralizing/scaling the obs stack (the per-host stack graduation noted in `CLAUDE.md` follow-ups) — separate, later.

## Design

### Component 1 — expose otel-collector self-metrics

`infra/observability/otel/otel-collector.yml` (plain `.yml`, not jinja) gains a `service.telemetry` block:

```yaml
service:
  telemetry:
    metrics:
      address: "0.0.0.0:8888"
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp/tempo]
```

`address: "0.0.0.0:8888"` is supported by the pinned collector (`otel/opentelemetry-collector:0.111.0`) and binds the internal Prometheus metrics to the container network so Prometheus can reach `otel-collector:8888`. No host port is published (in-network scrape only).

### Component 2 — scrape job

`infra/observability/prometheus/prometheus.yml.jinja` gains (always rendered — otel-collector is base obs):

```yaml
  - job_name: otel-collector
    static_configs:
      - targets: ["otel-collector:8888"]
```

### Component 3 — alert rules (new, always-present base files)

- `infra/observability/prometheus/alerts/otel_collector_alerts.yml`:
  ```yaml
  groups:
  - name: otel-collector
    rules:
    - alert: OtelCollectorDown
      expr: up{job="otel-collector"} == 0
      for: 5m
      labels: {severity: warning}
      annotations: {summary: "otel-collector scrape target is down — traces may be dropped; app-specific default, tune or remove"}
  ```
- `infra/observability/prometheus/alerts/prometheus_alerts.yml`:
  ```yaml
  groups:
  - name: prometheus
    rules:
    - alert: PrometheusDown
      expr: up{job="prometheus"} == 0
      for: 5m
      labels: {severity: warning}
      annotations: {summary: "Prometheus self-scrape is down"}
    - alert: PrometheusConfigReloadFailed
      expr: prometheus_config_last_reload_successful == 0
      for: 5m
      labels: {severity: warning}
      annotations: {summary: "Prometheus config reload failed — alerting/scrape config may be stale"}
  ```
  (Exact YAML formatting matched to the existing alert files in the plan.) Both files are unconditional (base infra), placed alongside `postgres_alerts.yml`.

### Component 4 — dashboards (new, always-present)

Minimal Grafana dashboards mirroring the existing exporter dashboards' shape (e.g. `redis.json` — a single `up{job="…"}` stat panel):
- `infra/observability/grafana/dashboards/otel-collector.json` — `uid: otel-collector`, a stat panel on `up{job="otel-collector"}`.
- `infra/observability/grafana/dashboards/prometheus.json` — `uid: prometheus`, a stat panel on `up{job="prometheus"}`.

Both unconditional `.json` (no jinja).

### Component 5 — completeness-guard framework test

`tests/test_obs_completeness.py` (framework-side, no Docker):
- Render an all-batteries project via `render_project`.
- Parse `infra/observability/prometheus/prometheus.yml` → the set of `job_name`s.
- For **every job except `app`**, assert:
  1. **scrape**: the job is present in `prometheus.yml` (definitionally true from the parse — the iteration set);
  2. **alert**: some file under `infra/observability/prometheus/alerts/*.yml` contains `job="<name>"` (an `up{job="<name>"}`-style rule);
  3. **dashboard**: some file under `infra/observability/grafana/dashboards/*.json` contains `job="<name>"`.
- This passes today for `postgres`/`celery`/`mongodb`/`redis`, goes green for `otel-collector`/`prometheus` once Components 1–4 land, and **fails for any future exporter-adding battery that ships a scrape job without a matching alert + dashboard** — the durable invariant.

The `app` job is excluded (application metrics; covered by `slo.json` + `slo_alerts.yml` on latency/error-rate, not an `up{job=...}` exporter pattern).

## Testing

- **Completeness-guard test** (Component 5) is itself the primary regression guard; written test-first (red on otel-collector/prometheus before Components 1–4, green after).
- **Compose/prometheus parse sanity**: the existing render tests + a YAML-parse assertion confirm `prometheus.yml` and `otel-collector.yml` stay valid.
- The existing acceptance tier still renders + runs the generated project (the obs stack is config, exercised by `docker compose config` merge validations there).

## Error handling / operational notes

- `address: "0.0.0.0:8888"` exposes metrics only on the container network (no published host port) — same posture as the other exporters.
- The new alert summaries carry the same "app-specific default; tune or remove" note as the existing exporter alerts (these are starting points, not prescriptions).
- `up{job="prometheus"}==0` can't fire when Prometheus is fully down (it can't evaluate) — it covers a momentary self-scrape gap; `PrometheusConfigReloadFailed` is the more actionable self-health signal and is the real value of the self-scrape.

## File changes (summary)

| File | Change |
|---|---|
| `infra/observability/otel/otel-collector.yml` | add `service.telemetry.metrics.address: "0.0.0.0:8888"` |
| `infra/observability/prometheus/prometheus.yml.jinja` | add `otel-collector` scrape job |
| `infra/observability/prometheus/alerts/otel_collector_alerts.yml` | new — OtelCollectorDown |
| `infra/observability/prometheus/alerts/prometheus_alerts.yml` | new — PrometheusDown + ConfigReloadFailed |
| `infra/observability/grafana/dashboards/otel-collector.json` | new — minimal up-stat |
| `infra/observability/grafana/dashboards/prometheus.json` | new — minimal up-stat |
| `tests/test_obs_completeness.py` (framework) | new — scrape+alert+dashboard guard |

## Risks

- **Collector telemetry syntax** — `service.telemetry.metrics.address` is correct for 0.111.0; confirm the rendered config parses + the collector starts (the acceptance/`docker compose config` path).
- **Guard over-strictness** — if a future job legitimately has no exporter-down semantics, the guard would need an explicit exclusion (like `app`). Documented in the test.
- **YAML/JSON validity** — render + parse the new files; keep dashboards minimal + valid Grafana schema.
- **Fixture safety** — these files aren't eval-fixture-anchored; re-run the per-fixture `git apply --check` scan (expect 0 broken).
