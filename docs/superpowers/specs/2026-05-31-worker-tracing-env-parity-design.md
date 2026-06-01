# Worker tracing + OTEL env-parity guard — design

**Date:** 2026-05-31
**Status:** approved (brainstorm) → ready for implementation plan
**Source finding:** template-audit `template-audit-2026-05-31-76d9b65` (observability-infra, high) — *"worker/beat in `services.yml` are missing `APP_OTEL_ENABLED`/`APP_OTEL_EXPORTER_OTLP_ENDPOINT` → no traces from workers in production."* Cross-refs the `CLAUDE.md` known follow-up *"environment-parity reviewer (dev→ci→stage→prod)."*

## Problem

Celery workers already emit **metrics** (the `celery-exporter` sidecar + the `celery` Prometheus scrape job), but emit **no distributed traces**:

- `observability/tracing.py::configure_tracing(app, settings)` is **FastAPI-specific** — it takes a `FastAPI` app and calls `FastAPIInstrumentor`. It runs only in the app process (from `create_app`).
- The Celery bootstrap (`tasks/app.py`) has **zero** OTEL wiring — no tracer provider, no `CeleryInstrumentor`.
- `worker`/`beat` carry **no** `APP_OTEL_*` env in **either** `dev.yml` or `services.yml` (only the `app` service is wired, via the `observability.yml` overlay).

Consequence: a task enqueued by a traced HTTP request loses the trace at the worker boundary, and worker-internal work is invisible to Tempo — in every environment. The audit's literal fix (add env vars to `services.yml`) is **necessary but not sufficient**: without an in-process OTEL bootstrap the env vars produce no spans.

This is partly an environment-parity gap (an obs surface wired for `app` but not its sibling app-image services) and partly an obs-completeness gap (an untraced runtime surface). The slice addresses the concrete worker-tracing gap **and** ships a framework-side regression guard for the parity class.

## Scope

**In scope**

1. Worker-side OTEL **tracing** (code), gated on `settings.otel_enabled`, fork-safe for Celery's prefork pool.
2. `APP_OTEL_*` env on `worker` + `beat` in `dev.yml` **and** `services.yml` (parity with `app`).
3. The `opentelemetry-instrumentation-celery` dependency (workers-gated).
4. A framework-side **env-parity guard test** asserting every app-image service carries the OTEL env wiring.

**Out of scope**

- The full LLM **env-parity review agent** (a separate, larger slice; this slice ships a focused test invariant instead).
- **Beat-process** span instrumentation — beat schedules/dispatches rather than executing task work, so its spans are low-value. Beat still receives the `APP_OTEL_*` env for config parity, but is not separately instrumented.
- Worker **metrics** — already covered by `celery-exporter`.

## Design

### Component 1 — refactor `observability/tracing.py`

Extract the provider/exporter setup so the FastAPI and worker paths share it:

- `_build_tracer_provider(settings) -> TracerProvider` — `Resource{service.name=settings.service_name}`, `BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True))`. Identical to today's app setup.
- `configure_tracing(app, settings)` — **unchanged behavior**: early-return when `not otel_enabled`; otherwise `_build_tracer_provider` + `trace.set_tracer_provider(provider)` + `FastAPIInstrumentor.instrument_app(app)`.
- `configure_worker_tracing(settings)` — **new**: early-return when `not otel_enabled`; otherwise `_build_tracer_provider` + `trace.set_tracer_provider(provider)` + `CeleryInstrumentor().instrument()`.

All OTel imports stay **lazy** (inside the functions) so a disabled app (tests, `dev:lite`, local uvicorn) never imports the SDK or starts an exporter.

### Component 2 — Celery worker bootstrap (`tasks/app.py`)

Register a `worker_process_init` signal handler that calls `configure_worker_tracing(get_settings())`. Rationale (the key fork): Celery's default prefork pool forks worker children, and `BatchSpanProcessor`'s background export thread does **not** survive a fork — so the provider must be built **after** fork, which is exactly when `worker_process_init` fires (once per worker child). Module-level/import-time init would be fork-unsafe (silent span loss); `celeryd_init` (pre-fork) has the same exporter-thread caveat. The handler is always registered; it is a no-op when `otel_enabled` is false (gating lives in `configure_worker_tracing`), so import stays clean.

### Component 3 — compose env (`dev.yml.jinja`, `services.yml.jinja`)

Add to **`worker`** and **`beat`** (workers-gated blocks) in both files:

```yaml
APP_OTEL_ENABLED: "true"
APP_OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
```

matching the `app` service's wiring (`observability.yml`). dev and prod/staging stay consistent.

### Component 4 — dependency (`pyproject.toml.jinja`)

Add `opentelemetry-instrumentation-celery` to the **`workers`-gated** runtime dependencies (the only consumer of `CeleryInstrumentor`).

### Component 5 — env-parity guard test (framework-side)

A framework test (`tests/`) that renders a `workers`+otel project and parses the compose YAML **per file (no Docker)**, asserting that every service running the app image — `app` (in `observability.yml`), `worker` + `beat` (in `dev.yml` and `services.yml`) — carries both `APP_OTEL_ENABLED` and `APP_OTEL_EXPORTER_OTLP_ENDPOINT`. This is a framework-authoring invariant: it guards the regression class ("an app-image service wired for obs in one place but not another"), scoped to OTEL env for now. It complements, but does not replace, the future env-parity review agent.

## Testing

- **Rendered-project hermetic unit test** (template `tests/`, workers-gated):
  - `configure_worker_tracing(settings)` is a no-op when `otel_enabled` is false (no provider set, no import side effects).
  - `_build_tracer_provider(settings)` returns a provider whose resource `service.name == settings.service_name`.
  - the `worker_process_init` handler is registered on the Celery app and only calls `configure_worker_tracing` when enabled.
- **Framework env-parity guard test** (Component 5) — renders + YAML-asserts the OTEL env on all app-image services.
- **Existing tiers** — the acceptance tier still renders the project and runs its suite + a clean first `pre-commit`; the cheap YAML test covers the parity assertion without the Docker tier.

## Error handling / operational notes

- All worker OTEL setup is gated on `otel_enabled`; with OTel off (tests/lite/local) nothing is imported or started.
- If the OTLP endpoint is unreachable, `BatchSpanProcessor` drops spans non-fatally — same posture as the app today.
- Worker spans use the same `service.name` as the app (single logical service); span/instrumentation attributes distinguish worker task spans from HTTP spans in Tempo.

## File changes (summary)

| File | Change |
|---|---|
| `src/{{package_name}}/observability/tracing.py` | extract `_build_tracer_provider`; add `configure_worker_tracing`; `configure_tracing` unchanged behavior |
| `src/{{package_name}}/{…workers…}tasks/app.py.jinja` | register `worker_process_init` → `configure_worker_tracing` |
| `infra/compose/dev.yml.jinja` | `APP_OTEL_*` on `worker` + `beat` |
| `infra/compose/services.yml.jinja` | `APP_OTEL_*` on `worker` + `beat` |
| `pyproject.toml.jinja` | `opentelemetry-instrumentation-celery` (workers-gated) |
| template `tests/unit/{…workers…}` | hermetic worker-tracing unit test |
| framework `tests/…` | env-parity OTEL guard test |

## Risks

- **Fork-safety** — mitigated by the `worker_process_init` mechanism (the central design decision).
- **Fixture/format churn** — the touched template files (`tracing.py`, `app.py.jinja`, compose, pyproject) are not anchored by many eval fixtures; verify no `change.patch` breakage (re-run the per-fixture `git apply --check` scan) and run `ruff format --check` on rendered output (the long-line regression class).
- **Acceptance `/tmp` wedge** — avoid the full Docker acceptance tier in-session per the standing caveat; rely on the hermetic + per-file YAML tests, plus a `docker compose config` merge spot-check if needed.
