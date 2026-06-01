# Data-store trace instrumentation — design

**Date:** 2026-05-31
**Status:** approved (brainstorm) → ready for implementation plan
**Source finding:** template-audit `template-audit-2026-05-31-76d9b65` (observability-db, 14× high) — repository read/write paths across `db`, `vectors`, `mongo`, `cache`, `timeseries`, `graph` have "no metric or span." First sub-slice of the deferred **obs-completeness** bucket (sub-slices B = obs-infra self-monitoring + completeness guard, C = small obs hygiene, follow separately).

## Problem

The generated app instruments **FastAPI** (and, after the worker-tracing slice, **Celery**) with OpenTelemetry, but the **data stores are not instrumented at all**:

- `MetricsRegistry` (`observability/metrics.py`) exposes only `record_request` (HTTP); there is no DB/query primitive.
- No repository or client module uses a tracer/span (`grep` for `start_as_current_span`/`get_tracer`/`record_query` in app code returns nothing).
- No `opentelemetry-instrumentation-{sqlalchemy,pymongo,redis}` packages are declared (only `-fastapi` and `-celery`).

So every SQLAlchemy query (postgres baseline + pgvector/timescaledb/age, which share the engine), every pymongo call, and every redis op produces **no span**. A traced HTTP request (or Celery task) shows nothing about the DB/store work it triggers — the `obs-db` cluster.

The obs-db agent's literal suggestion ("add `metrics.record_query()` or span") would, if taken as per-call Prometheus metrics, introduce high-cardinality metrics in ~14 hand-edited call sites — an antipattern and a maintenance burden. The idiomatic answer is **OpenTelemetry auto-instrumentation** of the store libraries, exactly mirroring how FastAPI and Celery are already handled.

## Scope

**In scope** — OpenTelemetry **trace** auto-instrumentation for the data stores, gated per battery, wired in both the app and worker tracing setup:
- SQLAlchemy (baseline postgres; also covers pgvector/timescaledb/age — same engine/session).
- pymongo (mongodb battery).
- redis (redis **or** workers battery).

**Out of scope**
- **Per-query Prometheus metrics** — high cardinality; an antipattern. Query latency/throughput is visible in traces (Tempo). The existing `/metrics` keeps request-level metrics.
- **Client-level `health()` functions** (an obs-db sub-finding) — already covered: the `/health` route pings mongo (`get_client().admin.command("ping")`) and redis (`get_redis().ping()`) directly. Adding `health()` to the client modules would be redundant. Verified false-positive.
- obs-infra self-monitoring (otel-collector scrape/alert, prometheus self-scrape alert) and the obs-completeness guard test — **sub-slice B**.
- `_latencies_ms` cap, GraphQL introspection logging — **sub-slice C**.
- The `review-observability` agent split / a new review agent — not this slice.

## Design

### Component 1 — dependencies (`pyproject.toml.jinja`)

- **Base** (always, postgres is baseline): `opentelemetry-instrumentation-sqlalchemy>=0.48b0`.
- **Battery-gated:** `opentelemetry-instrumentation-pymongo>=0.48b0` (`{% if "mongodb" in batteries %}`); `opentelemetry-instrumentation-redis>=0.48b0` (`{% if "redis" in batteries or "workers" in batteries %}`).

Version floor `>=0.48b0` matches the existing `opentelemetry-instrumentation-fastapi`/`-celery` pins.

### Component 2 — `observability/datastores.py.jinja` (new, jinja-gated)

A single entrypoint:

```python
def configure_datastore_instrumentation(settings: "Settings") -> None:
    """Auto-instrument the data stores for tracing (call once per process).

    No-op when OTel is disabled. SQLAlchemy is always instrumented (postgres baseline,
    shared by pgvector/timescaledb/age); pymongo/redis are instrumented when their
    battery is present. Lazy imports so a disabled process never imports the SDK.
    """
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from ..db.engine import engine

    SQLAlchemyInstrumentor().instrument(engine=engine)
    {%- if "mongodb" in batteries %}
    from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
    PymongoInstrumentor().instrument()
    {%- endif %}
    {%- if "redis" in batteries or "workers" in batteries %}
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    RedisInstrumentor().instrument()
    {%- endif %}
```

(Exact formatting/black-compliance resolved in the plan; the jinja blocks render only the present stores.) The module is **always present** (SQLAlchemy baseline); the jinja gates only the optional store blocks. The "form" decision (jinja-gated module vs `try/except ImportError` vs per-store self-instrumentation) resolved to the **jinja-gated module** — explicit, convention-aligned, keeps `tracing.py` plain.

### Component 3 — wiring (`observability/tracing.py`)

Both tracing entrypoints call the new function after building the provider:
- `configure_tracing(app, settings)` → `_build_tracer_provider`, `FastAPIInstrumentor.instrument_app(app)`, then `configure_datastore_instrumentation(settings)`.
- `configure_worker_tracing(settings)` → `_build_tracer_provider`, `CeleryInstrumentor().instrument()`, then `configure_datastore_instrumentation(settings)`.

The worker path matters: workers hit the DB (DLQ writes) and redis (broker/cache), so they must instrument the stores too. SQLAlchemy/pymongo/redis instrumentors patch globally (or per-engine for SQLAlchemy); each process calls once.

## Testing

Rendered-project hermetic unit tests (template `tests/unit/`, runs in a generated all-batteries or workers+stores project):
- `configure_datastore_instrumentation(Settings(otel_enabled=False))` is a no-op (no SDK import, no raise).
- Enabled path: monkeypatch `SQLAlchemyInstrumentor.instrument` / `PymongoInstrumentor.instrument` / `RedisInstrumentor.instrument` to record, call with `otel_enabled=True`, assert the expected set fired for the rendered battery combo (SQLAlchemy always; pymongo/redis when present). This verifies the gating without standing up real engines/clients.
- The FastAPI + worker tracing tests still pass (no regression) — `configure_tracing`/`configure_worker_tracing` now also call the datastore entrypoint.

The existing acceptance tier still renders + runs the generated project (incl. its DB-backed tests via testcontainers); the hermetic tests above are the fast-tier guard.

## Error handling / operational notes

- All instrumentation gated on `otel_enabled`; disabled processes import nothing.
- SQLAlchemy binds to the module-level `db.engine.engine`; pymongo/redis patch their libraries globally.
- Calling an instrumentor twice in one process warns (OTel) but is harmless; app and worker are separate processes that each call once.
- Spans carry the SQL statement / mongo command / redis command + latency; they continue the trace from the triggering FastAPI request or Celery task (context propagation is automatic once both ends are instrumented).

## File changes (summary)

| File | Change |
|---|---|
| `pyproject.toml.jinja` | base `…-sqlalchemy`; battery-gated `…-pymongo`, `…-redis` |
| `src/{{package_name}}/observability/datastores.py.jinja` | new — `configure_datastore_instrumentation` |
| `src/{{package_name}}/observability/tracing.py` | both entrypoints call the datastore instrumentation |
| template `tests/unit/{…datastore…}` | hermetic gating tests |

## Risks

- **Instrumentor API drift** — `SQLAlchemyInstrumentor().instrument(engine=...)` is the documented binding; confirm against the pinned version in the plan.
- **Format/long-line regression** — run `ruff format --check` on the rendered module (the recurring long-line class).
- **Fixture safety** — these files aren't eval-fixture-anchored; re-run the per-fixture `git apply --check` scan to confirm 0 broken.
- **Acceptance `/tmp` wedge** — avoid the Docker acceptance tier in-session; rely on hermetic tests + a render/import check.
