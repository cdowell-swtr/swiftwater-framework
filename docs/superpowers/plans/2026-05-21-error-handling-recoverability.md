# Error Handling & Recoverability Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generated projects ship an error-handling & recoverability toolkit from day one — an RFC 7807 global exception handler, a `tenacity` retry decorator, a `pybreaker` circuit breaker, graceful shutdown, and first-class recoverability metrics on `/metrics` — that builders extend rather than create.

**Architecture:** All new code is **template payload** under `src/framework_cli/template/src/{{package_name}}/`, validated by rendering a project and running its own test suite (plus a framework-side render assertion). A module-level `RecoverabilityMetrics` singleton (in `observability/recoverability.py`) is fed by the exception handler, retry decorator, and circuit-breaker listener, and is appended to the existing per-app Prometheus exposition by the `/metrics` route. The exception handler, retry, and breaker are independent scaffolds (the spec's "builders extend them, not create them") — they are exercised by their own tests, not yet wired to a concrete call path. Graceful shutdown is a FastAPI `lifespan` hook that disposes the SQLAlchemy engine on `SIGTERM` (uvicorn translates the signal into ASGI lifespan shutdown; the container `entrypoint.sh` already `exec`s uvicorn as PID 1, so the signal reaches it).

**Tech Stack:** Python 3.12, FastAPI/Starlette, `tenacity` (retry), `pybreaker` (circuit breaker), `structlog`, `pydantic`. Tests: `pytest` + FastAPI `TestClient`. Package/build: `uv`, `hatchling`. Generated-project gates: `ruff`, `mypy` (defaults — not strict), coverage ≥ 70%.

**Source spec:** `docs/superpowers/specs/2026-05-20-framework-design.md` §19 (Error Handling & Recoverability Scaffold), §8 (Recoverability Metrics, Structured Logging), §4 (CLAUDE.md conventions). Roadmap row: Plan 4 in `docs/superpowers/plans/2026-05-20-meta-plan.md`.

---

## Scope & Non-Goals

**In scope (the four no-battery patterns from §19 + their recoverability metrics):**
1. Global exception handler → RFC 7807 `application/problem+json`, logs with context + correlation id, increments an unhandled-exception counter.
2. Retry decorator (`tenacity`) → exponential backoff + jitter, logs each attempt, records attempts / recovered / exhausted.
3. Circuit breaker (`pybreaker`) → state exposed on `/metrics` as a gauge, transitions logged.
4. Graceful shutdown → `lifespan` shutdown disposes the DB engine and logs.
5. Recoverability metrics → exposed on `/metrics` (first-class per §8): unhandled exceptions, retry attempts/recovered/exhausted, circuit-breaker state.

**Explicit non-goals (deferred, with rationale):**
- **Dead Letter Queue** — deferred to **Plan 8 (`workers` battery)**. A DLQ needs a task broker (Celery/Redis); there are no workers in the current scaffold to feed it. (Confirmed with the user during planning.)
- **`recovery_rate_pct` as a `/health` SLO** — the §8 `/health` example shows it, but the current SLO model (`observability/slo.py`) is strictly "lower current is worse" (`current > threshold → breached`); recovery rate is "higher is better", so adding it requires a directional SLO-model extension **and** regenerating the Plan 3b provisioning artifacts (Grafana dashboard + Prometheus alerts) and updating the drift guard. That is a clean, separable enhancement, out of scope here. Recovery is still observable: `app_retries_recovered_total` / `app_retries_exhausted_total` are on `/metrics`, so a recovery-rate panel can be computed in Grafana from them.
- **MTTR per error class** and **graceful-degradation-event** metrics (§8) — require richer instrumentation/labels than the deliberately label-light in-process registry; deferred.

**Critical conventions (from the repo's CLAUDE.md):** files under `src/framework_cli/template/` are template *payload*, not framework source — the framework's own `mypy`/`ruff` exclude them. They are validated only by rendering + running the generated project. Brace-named paths (`{{package_name}}`) are Copier path templating — leave them. `.py` files inside the template that are **not** interpolated keep a plain `.py` extension (no `.jinja`); files that contain `{{ package_name }}` (or other Copier vars) get a `.jinja` suffix so Copier renders them. Each new file below is marked accordingly.

---

## File Structure

New template-payload files (rendered into every generated project):

| File | Suffix | Responsibility |
|---|---|---|
| `src/{{package_name}}/observability/recoverability.py` | `.py` (no vars) | Module-level `RecoverabilityMetrics` singleton: counters + circuit-breaker gauge + Prometheus render + reset. |
| `src/{{package_name}}/middleware/errors.py` | `.py` (no vars) | RFC 7807 handlers (unhandled `Exception`, `HTTPException`, `RequestValidationError`) + `register_exception_handlers(app)`. |
| `src/{{package_name}}/resilience/__init__.py` | `.py` | Package marker. |
| `src/{{package_name}}/resilience/retry.py` | `.py` (no vars) | `with_retry(...)` decorator over `tenacity`; records recoverability metrics; logs attempts. |
| `src/{{package_name}}/resilience/circuit_breaker.py` | `.py` (no vars) | `build_breaker(...)` over `pybreaker`; listener logs transitions + updates the gauge. |
| `tests/unit/test_recoverability.py.jinja` | `.jinja` (imports `{{ package_name }}`) | Unit tests for `RecoverabilityMetrics`. |
| `tests/unit/test_retry.py.jinja` | `.jinja` | Unit tests for `with_retry`. |
| `tests/unit/test_circuit_breaker.py.jinja` | `.jinja` | Unit tests for `build_breaker`. |
| `tests/functional/test_error_handling.py.jinja` | `.jinja` | Functional tests for the RFC 7807 handlers + `/metrics` recoverability lines. |
| `tests/functional/test_graceful_shutdown.py.jinja` | `.jinja` | Functional test for lifespan shutdown disposing the engine. |

Modified template-payload files:

| File | Change |
|---|---|
| `src/{{package_name}}/main.py.jinja` | Add `lifespan` (graceful shutdown), call `register_exception_handlers(app)`. |
| `src/{{package_name}}/middleware/observability.py` | Set `request.state.correlation_id = cid` so the exception handler can read it. |
| `src/{{package_name}}/routes/health.py.jinja` | `/metrics` appends `recoverability.render_prometheus()`. |
| `src/{{package_name}}/db/engine.py` | Add `dispose_engine()`. |
| `tests/conftest.py.jinja` | Add an autouse fixture that resets the recoverability singleton between tests. |
| `pyproject.toml.jinja` | Add `tenacity` and `pybreaker` runtime deps. |
| `CLAUDE.md.jinja` | Add an "Error handling & recoverability" subsection inside the `FRAMEWORK:BEGIN/END` managed block. |

Modified framework-source test (validates the template renders the scaffold):

| File | Change |
|---|---|
| `tests/test_copier_runner.py` | Add `test_render_includes_resilience_scaffold`. |

---

## How to render & run during execution

The implementer renders a throwaway project and runs its suite. Use a scratch dir, e.g.:

```bash
# from the repo root
uv run python -c "from framework_cli.copier_runner import render_project; from pathlib import Path; render_project(Path('/tmp/demo'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12'})"
cd /tmp/demo && uv sync
```

Then run individual tests inside `/tmp/demo` with `uv run pytest tests/unit/test_retry.py -v`, etc. The DB-backed fixtures (`engine`, `db_session`) need Docker (testcontainers Postgres); the tests added by this plan do **not** use them, so they run without Docker. Re-render after each template edit (Copier does not hot-reload). Delete `/tmp/demo` between renders or render to a fresh path.

> Each task's "Run" commands assume the project was (re-)rendered to `/tmp/demo` and `uv sync`'d after the template edits in that task.

---

## Task 1: Recoverability metrics singleton + autouse reset

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/observability/recoverability.py`
- Test: `src/framework_cli/template/tests/unit/test_recoverability.py.jinja`
- Modify: `src/framework_cli/template/tests/conftest.py.jinja`

- [ ] **Step 1: Write the failing unit test**

Create `src/framework_cli/template/tests/unit/test_recoverability.py.jinja`:

```python
from {{ package_name }}.observability.recoverability import RecoverabilityMetrics


def test_fresh_registry_reports_zeros():
    m = RecoverabilityMetrics()
    snap = m.snapshot()
    assert snap == {
        "unhandled": 0,
        "retry_attempts": 0,
        "retries_recovered": 0,
        "retries_exhausted": 0,
    }


def test_counters_increment():
    m = RecoverabilityMetrics()
    m.record_unhandled_exception()
    m.record_retry_attempt()
    m.record_retry_attempt()
    m.record_retry_recovered()
    m.record_retry_exhausted()
    snap = m.snapshot()
    assert snap["unhandled"] == 1
    assert snap["retry_attempts"] == 2
    assert snap["retries_recovered"] == 1
    assert snap["retries_exhausted"] == 1


def test_circuit_state_defaults_to_closed_zero():
    m = RecoverabilityMetrics()
    assert m.circuit_state("svc") == 0  # unknown breaker -> closed


def test_set_circuit_state_maps_names_to_numbers():
    m = RecoverabilityMetrics()
    m.set_circuit_state("svc", "open")
    assert m.circuit_state("svc") == 1
    m.set_circuit_state("svc", "half-open")
    assert m.circuit_state("svc") == 2
    m.set_circuit_state("svc", "closed")
    assert m.circuit_state("svc") == 0


def test_render_prometheus_emits_counters_and_breaker_gauge():
    m = RecoverabilityMetrics()
    m.record_unhandled_exception()
    m.set_circuit_state("payments", "open")
    text = m.render_prometheus()
    assert "# TYPE app_unhandled_exceptions_total counter" in text
    assert "app_unhandled_exceptions_total 1\n" in text
    assert "app_retry_attempts_total 0\n" in text
    assert "# TYPE app_circuit_breaker_state gauge" in text
    assert 'app_circuit_breaker_state{name="payments"} 1\n' in text


def test_render_prometheus_omits_gauge_when_no_breakers():
    text = RecoverabilityMetrics().render_prometheus()
    assert "app_circuit_breaker_state" not in text


def test_reset_clears_everything():
    m = RecoverabilityMetrics()
    m.record_unhandled_exception()
    m.set_circuit_state("svc", "open")
    m.reset()
    assert m.snapshot()["unhandled"] == 0
    assert "app_circuit_breaker_state" not in m.render_prometheus()
```

- [ ] **Step 2: Run it to confirm it fails**

Re-render to `/tmp/demo`, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/unit/test_recoverability.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'demo.observability.recoverability'`.

- [ ] **Step 3: Implement the module**

Create `src/framework_cli/template/src/{{package_name}}/observability/recoverability.py`:

```python
"""Process-wide recoverability metrics (first-class per the design spec).

A module-level singleton, distinct from the per-app request `MetricsRegistry`, because the
retry decorator and circuit-breaker listener are wired at import time, decoupled from any
FastAPI app instance. The `/metrics` route appends `render_prometheus()` to the per-app
exposition. Deliberately label-light to match the in-process registry's simplicity.
"""

from __future__ import annotations

import threading

_CB_STATE_VALUES = {"closed": 0, "open": 1, "half-open": 2}

_COUNTER_TEMPLATE = (
    "# HELP app_unhandled_exceptions_total Unhandled exceptions caught by the global handler\n"
    "# TYPE app_unhandled_exceptions_total counter\n"
    "app_unhandled_exceptions_total {unhandled}\n"
    "# HELP app_retry_attempts_total Retry attempts scheduled by with_retry\n"
    "# TYPE app_retry_attempts_total counter\n"
    "app_retry_attempts_total {attempts}\n"
    "# HELP app_retries_recovered_total Calls that succeeded after at least one retry\n"
    "# TYPE app_retries_recovered_total counter\n"
    "app_retries_recovered_total {recovered}\n"
    "# HELP app_retries_exhausted_total Calls that exhausted all retries and failed\n"
    "# TYPE app_retries_exhausted_total counter\n"
    "app_retries_exhausted_total {exhausted}\n"
)

_CB_HEADER = (
    "# HELP app_circuit_breaker_state Circuit breaker state (0=closed, 1=open, 2=half-open)\n"
    "# TYPE app_circuit_breaker_state gauge\n"
)


class RecoverabilityMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._unhandled = 0
        self._retry_attempts = 0
        self._retries_recovered = 0
        self._retries_exhausted = 0
        self._cb_states: dict[str, int] = {}

    def record_unhandled_exception(self) -> None:
        with self._lock:
            self._unhandled += 1

    def record_retry_attempt(self) -> None:
        with self._lock:
            self._retry_attempts += 1

    def record_retry_recovered(self) -> None:
        with self._lock:
            self._retries_recovered += 1

    def record_retry_exhausted(self) -> None:
        with self._lock:
            self._retries_exhausted += 1

    def set_circuit_state(self, name: str, state_name: str) -> None:
        with self._lock:
            self._cb_states[name] = _CB_STATE_VALUES[state_name]

    def circuit_state(self, name: str) -> int:
        with self._lock:
            return self._cb_states.get(name, 0)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "unhandled": self._unhandled,
                "retry_attempts": self._retry_attempts,
                "retries_recovered": self._retries_recovered,
                "retries_exhausted": self._retries_exhausted,
            }

    def render_prometheus(self) -> str:
        with self._lock:
            text = _COUNTER_TEMPLATE.format(
                unhandled=self._unhandled,
                attempts=self._retry_attempts,
                recovered=self._retries_recovered,
                exhausted=self._retries_exhausted,
            )
            if self._cb_states:
                text += _CB_HEADER
                for name, value in sorted(self._cb_states.items()):
                    text += f'app_circuit_breaker_state{{name="{name}"}} {value}\n'
            return text

    def reset(self) -> None:
        with self._lock:
            self._unhandled = 0
            self._retry_attempts = 0
            self._retries_recovered = 0
            self._retries_exhausted = 0
            self._cb_states.clear()


recoverability = RecoverabilityMetrics()
"""The process-wide singleton imported by the exception handler, retry decorator, breaker, and /metrics."""
```

- [ ] **Step 4: Add the autouse reset fixture**

The singleton accumulates across tests. Add an autouse fixture so every test starts clean. In `src/framework_cli/template/tests/conftest.py.jinja`, the imports at the top currently are:

```python
import os
import subprocess
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from {{ package_name }}.db.engine import build_engine
```

Add this fixture immediately after that import block (before the `pg_url` fixture):

```python
@pytest.fixture(autouse=True)
def _reset_recoverability() -> Iterator[None]:
    """Recoverability metrics live in a module-level singleton; reset around each test."""
    from {{ package_name }}.observability.recoverability import recoverability

    recoverability.reset()
    yield
    recoverability.reset()
```

- [ ] **Step 5: Run the test to confirm it passes**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/unit/test_recoverability.py -q`
Expected: PASS (7 passed).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/src src/framework_cli/template/tests/unit/test_recoverability.py.jinja src/framework_cli/template/tests/conftest.py.jinja
git commit -m "feat(template): recoverability metrics singleton + autouse reset"
```

(The pre-commit hook requires `CLAUDE.md` staged — update the Current State pointer per the repo's working agreement, or stage it with `git add CLAUDE.md`, before committing. This applies to every commit below.)

---

## Task 2: RFC 7807 global exception handler + /metrics exposure

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/middleware/errors.py`
- Modify: `src/framework_cli/template/src/{{package_name}}/middleware/observability.py`
- Modify: `src/framework_cli/template/src/{{package_name}}/main.py.jinja`
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja`
- Test: `src/framework_cli/template/tests/functional/test_error_handling.py.jinja`

**Background — Starlette flow (so the handler placement is correct):** Starlette wraps the app as `ServerErrorMiddleware` (outermost) → user middleware (our `ObservabilityMiddleware`) → `ExceptionMiddleware` (innermost). A handler registered for `Exception`/`500` is invoked by `ServerErrorMiddleware`; handlers for `HTTPException`/`RequestValidationError` are invoked by `ExceptionMiddleware`. So: an unhandled error propagates up through `ObservabilityMiddleware` (which records a 500 and re-raises) to `ServerErrorMiddleware`, which calls our 500 handler. An `HTTPException` is converted by `ExceptionMiddleware` *below* `ObservabilityMiddleware`, so the middleware sees a normal 4xx response. `ObservabilityMiddleware` resets the correlation-id contextvar before re-raising, so the 500 handler must read the id from `request.state` (set in Step 2 below), not the contextvar.

- [ ] **Step 1: Write the failing functional test**

Create `src/framework_cli/template/tests/functional/test_error_handling.py.jinja`:

```python
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from {{ package_name }}.main import create_app
from {{ package_name }}.observability.recoverability import recoverability


def _app_with_failing_routes() -> FastAPI:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom-internal-detail")

    @app.get("/teapot")
    def teapot() -> None:
        raise HTTPException(status_code=418, detail="I'm a teapot")

    @app.get("/needs-int")
    def needs_int(n: int) -> dict[str, int]:
        return {"n": n}

    return app


def test_unhandled_exception_returns_problem_json():
    client = TestClient(_app_with_failing_routes(), raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 500
    assert body["title"] == "Internal Server Error"
    assert body["instance"] == "/boom"
    assert body["correlation_id"]  # populated from request.state by the middleware
    assert "kaboom-internal-detail" not in r.text  # internal detail never leaked


def test_http_exception_uses_problem_json():
    client = TestClient(_app_with_failing_routes())
    r = client.get("/teapot")
    assert r.status_code == 418
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["detail"] == "I'm a teapot"


def test_validation_error_uses_problem_json():
    client = TestClient(_app_with_failing_routes())
    r = client.get("/needs-int", params={"n": "not-an-int"})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "errors" in r.json()


def test_unhandled_exception_increments_metric_and_is_on_metrics_endpoint():
    client = TestClient(_app_with_failing_routes(), raise_server_exceptions=False)
    client.get("/boom")
    assert recoverability.snapshot()["unhandled"] == 1
    metrics_body = client.get("/metrics").text
    assert "app_unhandled_exceptions_total 1" in metrics_body
```

- [ ] **Step 2: Run it to confirm it fails**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/functional/test_error_handling.py -q`
Expected: FAIL — `ImportError`/`ModuleNotFoundError` for `errors`, or assertion failures (no problem+json, no `correlation_id`).

- [ ] **Step 3: Create the exception handlers**

Create `src/framework_cli/template/src/{{package_name}}/middleware/errors.py`:

```python
"""Global exception handling → RFC 7807 Problem Details (application/problem+json).

Registered on the app by `register_exception_handlers`. Three handlers give every error class
a consistent body: unhandled exceptions (500, detail never leaked), HTTPException (its status +
detail), and request validation errors (422 + the field errors). Each response carries the
request correlation id (read from request.state, set by ObservabilityMiddleware) so a failing
response is traceable to its logs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from ..logging_config import get_logger
from ..observability.recoverability import recoverability

if TYPE_CHECKING:
    from fastapi import FastAPI

_PROBLEM_MEDIA_TYPE = "application/problem+json"
_log = get_logger()


def _problem(
    *, status: int, title: str, detail: str, request: Request, **extra: Any
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    cid = getattr(request.state, "correlation_id", None)
    if cid:
        body["correlation_id"] = cid
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=_PROBLEM_MEDIA_TYPE)


async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    recoverability.record_unhandled_exception()
    _log.error(
        "unhandled_exception",
        error_type=type(exc).__name__,
        method=request.method,
        path=request.url.path,
    )
    # Never leak internal exception text to the client.
    return _problem(
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
        request=request,
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # registered only for this type
    detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return _problem(
        status=exc.status_code,
        title=detail,
        detail=detail,
        request=request,
    )


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # registered only for this type
    return _problem(
        status=422,
        title="Unprocessable Entity",
        detail="Request validation failed.",
        request=request,
        errors=exc.errors(),
    )


def register_exception_handlers(app: "FastAPI") -> None:
    """Wire the RFC 7807 handlers onto the app. Call once in create_app."""
    app.add_exception_handler(Exception, handle_unhandled_exception)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
```

> **Why `exc: Exception` + `assert isinstance(...)`:** Starlette types exception handlers as `Callable[[Request, Exception], ...]`. Annotating the parameter as the narrow type would trip `mypy` on the `add_exception_handler` call (parameter contravariance). Annotating `Exception` and narrowing with `isinstance` keeps `mypy` clean and is safe — Starlette only routes the registered type to each handler. The `errors()` payload from `RequestValidationError` is JSON-serializable.

- [ ] **Step 4: Have the middleware stash the correlation id on request.state**

In `src/framework_cli/template/src/{{package_name}}/middleware/observability.py`, the `dispatch` method currently sets the contextvar:

```python
        cid = request.headers.get(_CORRELATION_HEADER) or uuid.uuid4().hex
        token = correlation_id_var.set(cid)
```

Add a line right after, so the id survives the contextvar reset and is reachable by the 500 handler:

```python
        cid = request.headers.get(_CORRELATION_HEADER) or uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        request.state.correlation_id = cid
```

- [ ] **Step 5: Register the handlers in create_app**

In `src/framework_cli/template/src/{{package_name}}/main.py.jinja`, add the import (with the other middleware import) and the registration call. After:

```python
from {{ package_name }}.middleware.observability import ObservabilityMiddleware
```

add:

```python
from {{ package_name }}.middleware.errors import register_exception_handlers
```

and inside `create_app`, after `app.add_middleware(ObservabilityMiddleware, metrics=app.state.metrics)`, add:

```python
    register_exception_handlers(app)
```

(Imports must stay sorted/grouped to satisfy `ruff` — `errors` sorts before `observability`, so place the `errors` import line above the `observability` import line.)

- [ ] **Step 6: Append recoverability metrics to /metrics**

In `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja`, add the import after the existing `slo` import:

```python
from {{ package_name }}.observability.recoverability import recoverability
```

and change the `metrics` view body from:

```python
    return PlainTextResponse(
        request.app.state.metrics.render_prometheus(),
        status_code=200,
        media_type="text/plain; version=0.0.4",
    )
```

to:

```python
    body = request.app.state.metrics.render_prometheus() + recoverability.render_prometheus()
    return PlainTextResponse(
        body,
        status_code=200,
        media_type="text/plain; version=0.0.4",
    )
```

- [ ] **Step 7: Run the new + existing tests**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/functional/test_error_handling.py tests/functional/test_health.py tests/functional/test_correlation_id.py -q`
Expected: PASS (all green — the existing `/metrics` and correlation-id tests still pass; recoverability lines are appended, `app_up 1` / `app_requests_total` unchanged).

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/src src/framework_cli/template/tests/functional/test_error_handling.py.jinja
git commit -m "feat(template): RFC 7807 global exception handler + recoverability on /metrics"
```

---

## Task 3: Retry decorator (tenacity)

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/resilience/__init__.py`
- Create: `src/framework_cli/template/src/{{package_name}}/resilience/retry.py`
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Test: `src/framework_cli/template/tests/unit/test_retry.py.jinja`

- [ ] **Step 1: Add the tenacity dependency**

In `src/framework_cli/template/pyproject.toml.jinja`, in `[project].dependencies`, add `tenacity` after the `psycopg` line:

```toml
    "psycopg[binary]>=3.2",
    "tenacity>=9.0",
```

- [ ] **Step 2: Write the failing unit test**

Create `src/framework_cli/template/tests/unit/test_retry.py.jinja`:

```python
import pytest

from {{ package_name }}.observability.recoverability import recoverability
from {{ package_name }}.resilience.retry import with_retry

# Tiny waits keep the test fast; backoff behaviour itself is tenacity's, not ours to re-test.
_FAST = {"initial_wait": 0.001, "max_wait": 0.005}


def test_recovers_after_transient_failures():
    calls = {"n": 0}

    @with_retry(max_attempts=3, **_FAST)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3
    snap = recoverability.snapshot()
    assert snap["retry_attempts"] == 2  # two retries scheduled before success
    assert snap["retries_recovered"] == 1
    assert snap["retries_exhausted"] == 0


def test_no_retry_metrics_when_first_call_succeeds():
    @with_retry(max_attempts=3, **_FAST)
    def fine() -> int:
        return 42

    assert fine() == 42
    snap = recoverability.snapshot()
    assert snap["retry_attempts"] == 0
    assert snap["retries_recovered"] == 0


def test_exhausts_and_reraises_original_exception():
    @with_retry(max_attempts=2, **_FAST)
    def always_fail() -> None:
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        always_fail()
    snap = recoverability.snapshot()
    assert snap["retry_attempts"] == 1  # one retry between the two attempts
    assert snap["retries_exhausted"] == 1
    assert snap["retries_recovered"] == 0


def test_only_retries_listed_exceptions():
    @with_retry(max_attempts=3, exceptions=(KeyError,), **_FAST)
    def wrong_error() -> None:
        raise ValueError("not retried")

    with pytest.raises(ValueError):
        wrong_error()
    # ValueError is not in `exceptions`, so it propagates immediately — no retry, no exhausted.
    assert recoverability.snapshot()["retry_attempts"] == 0
    assert recoverability.snapshot()["retries_exhausted"] == 0
```

- [ ] **Step 3: Run it to confirm it fails**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/unit/test_retry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'demo.resilience'`.

- [ ] **Step 4: Implement the package + decorator**

Create `src/framework_cli/template/src/{{package_name}}/resilience/__init__.py`:

```python
"""Resilience scaffolds: retry and circuit breaker. Builders extend these, not create them."""
```

Create `src/framework_cli/template/src/{{package_name}}/resilience/retry.py`:

```python
"""Retry with exponential backoff + jitter, built on tenacity.

`with_retry` is a decorator factory. It logs every retry and records recoverability metrics:
each scheduled retry, whether the call eventually recovered (succeeded after >=1 retry), and
whether it exhausted all attempts. Defaults are sensible for an I/O call; override per use.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TypeVar

from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ..logging_config import get_logger
from ..observability.recoverability import recoverability

T = TypeVar("T")
_log = get_logger()


def with_retry(
    *,
    max_attempts: int = 3,
    initial_wait: float = 0.1,
    max_wait: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorate a callable to retry on `exceptions` with backoff + jitter.

    Re-raises the original exception once attempts are exhausted (no tenacity wrapper exception).
    """

    def _before_sleep(state: RetryCallState) -> None:
        recoverability.record_retry_attempt()
        _log.warning(
            "retrying",
            attempt=state.attempt_number,
            callable=getattr(state.fn, "__name__", "?"),
        )

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> T:
            retryer = Retrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential_jitter(initial=initial_wait, max=max_wait),
                retry=retry_if_exception_type(exceptions),
                before_sleep=_before_sleep,
                reraise=True,
            )
            try:
                result: T = retryer(fn, *args, **kwargs)
            except exceptions:
                recoverability.record_retry_exhausted()
                raise
            if retryer.statistics.get("attempt_number", 1) > 1:
                recoverability.record_retry_recovered()
            return result

        return wrapper

    return decorator
```

> **Notes:** `Retrying(...)` is callable — `retryer(fn, *args, **kwargs)` runs `fn` under the retry policy and returns its value; `retryer.statistics["attempt_number"]` is the total attempts made (`> 1` ⇒ it recovered after a failure). `before_sleep` fires once per scheduled retry. With `reraise=True`, the original exception is raised on exhaustion (not a `RetryError`), so callers catch what they expect.

- [ ] **Step 5: Run the test to confirm it passes**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/unit/test_retry.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/src src/framework_cli/template/pyproject.toml.jinja src/framework_cli/template/tests/unit/test_retry.py.jinja
git commit -m "feat(template): tenacity-based with_retry decorator + retry metrics"
```

---

## Task 4: Circuit breaker (pybreaker)

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/resilience/circuit_breaker.py`
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Test: `src/framework_cli/template/tests/unit/test_circuit_breaker.py.jinja`

- [ ] **Step 1: Add the pybreaker dependency**

In `src/framework_cli/template/pyproject.toml.jinja`, in `[project].dependencies`, add `pybreaker` after the `tenacity` line:

```toml
    "tenacity>=9.0",
    "pybreaker>=1.2",
```

- [ ] **Step 2: Write the failing unit test**

Create `src/framework_cli/template/tests/unit/test_circuit_breaker.py.jinja`:

```python
import pybreaker
import pytest

from {{ package_name }}.observability.recoverability import recoverability
from {{ package_name }}.resilience.circuit_breaker import build_breaker


def test_new_breaker_reports_closed_state():
    build_breaker(name="svc-a", fail_max=2, reset_timeout=60)
    assert recoverability.circuit_state("svc-a") == 0  # closed


def test_breaker_opens_after_fail_max_and_gauge_reflects_it():
    breaker = build_breaker(name="svc-b", fail_max=2, reset_timeout=60)

    def boom() -> None:
        raise RuntimeError("dependency down")

    # Two consecutive failures trip the breaker open.
    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(boom)

    assert recoverability.circuit_state("svc-b") == 1  # open

    # While open, calls fail fast with CircuitBreakerError (the dependency isn't called).
    with pytest.raises(pybreaker.CircuitBreakerError):
        breaker.call(boom)


def test_metrics_render_includes_breaker_gauge_line():
    build_breaker(name="svc-c", fail_max=1, reset_timeout=60)
    assert 'app_circuit_breaker_state{name="svc-c"} 0' in recoverability.render_prometheus()
```

- [ ] **Step 3: Run it to confirm it fails**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/unit/test_circuit_breaker.py -q`
Expected: FAIL — `ModuleNotFoundError` for `circuit_breaker` (and/or `pybreaker` import).

- [ ] **Step 4: Implement the breaker factory**

Create `src/framework_cli/template/src/{{package_name}}/resilience/circuit_breaker.py`:

```python
"""Circuit breaker built on pybreaker.

`build_breaker` returns a named CircuitBreaker whose state transitions are logged and mirrored
into the recoverability metrics gauge (exposed on /metrics). Wrap calls to an unstable
dependency: `breaker.call(fn, *args)` or use `@breaker` as a decorator. When open, calls fail
fast with pybreaker.CircuitBreakerError instead of hammering the failing dependency.
"""

from __future__ import annotations

import pybreaker

from ..logging_config import get_logger
from ..observability.recoverability import recoverability

_log = get_logger()


class _MetricsListener(pybreaker.CircuitBreakerListener):
    """Logs every state transition and updates the recoverability gauge."""

    def __init__(self, name: str) -> None:
        self._name = name

    def state_change(
        self,
        cb: pybreaker.CircuitBreaker,
        old_state: pybreaker.CircuitBreakerState,
        new_state: pybreaker.CircuitBreakerState,
    ) -> None:
        recoverability.set_circuit_state(self._name, new_state.name)
        _log.warning(
            "circuit_breaker_state_change",
            breaker=self._name,
            old_state=old_state.name,
            new_state=new_state.name,
        )


def build_breaker(
    *, name: str = "default", fail_max: int = 5, reset_timeout: float = 30.0
) -> pybreaker.CircuitBreaker:
    breaker = pybreaker.CircuitBreaker(
        fail_max=fail_max,
        reset_timeout=reset_timeout,
        name=name,
        listeners=[_MetricsListener(name)],
    )
    # Seed the gauge: pybreaker fires state_change only on transitions, not at construction.
    recoverability.set_circuit_state(name, "closed")
    return breaker
```

> **Note:** pybreaker state objects expose `.name` as one of `"closed"`, `"open"`, `"half-open"` — exactly the keys `RecoverabilityMetrics.set_circuit_state` maps. `build_breaker` takes keyword-only args; the test calls `build_breaker(name="svc-a", fail_max=2, reset_timeout=60)`.

- [ ] **Step 5: Run the test to confirm it passes**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/unit/test_circuit_breaker.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/src src/framework_cli/template/pyproject.toml.jinja src/framework_cli/template/tests/unit/test_circuit_breaker.py.jinja
git commit -m "feat(template): pybreaker circuit breaker with state on /metrics"
```

---

## Task 5: Graceful shutdown (lifespan + engine disposal)

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/db/engine.py`
- Modify: `src/framework_cli/template/src/{{package_name}}/main.py.jinja`
- Test: `src/framework_cli/template/tests/functional/test_graceful_shutdown.py.jinja`

- [ ] **Step 1: Write the failing functional test**

Create `src/framework_cli/template/tests/functional/test_graceful_shutdown.py.jinja`:

```python
from fastapi.testclient import TestClient

from {{ package_name }}.main import create_app


def test_lifespan_disposes_engine_on_shutdown(monkeypatch):
    calls: list[str] = []
    # The lifespan imports dispose_engine at shutdown; patch the attribute it looks up.
    monkeypatch.setattr(
        "{{ package_name }}.db.engine.dispose_engine", lambda: calls.append("disposed")
    )

    # Using TestClient as a context manager runs startup on enter and shutdown on exit.
    with TestClient(create_app()) as client:
        assert client.get("/heartbeat").status_code == 200

    assert calls == ["disposed"]
```

- [ ] **Step 2: Run it to confirm it fails**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/functional/test_graceful_shutdown.py -q`
Expected: FAIL — `AttributeError: <module 'demo.db.engine'> has no attribute 'dispose_engine'` (the monkeypatch target doesn't exist yet).

- [ ] **Step 3: Add dispose_engine to db/engine.py**

In `src/framework_cli/template/src/{{package_name}}/db/engine.py`, after the `get_session` function at the bottom, add:

```python
def dispose_engine() -> None:
    """Dispose the engine's connection pool — called on graceful shutdown."""
    engine.dispose()
```

- [ ] **Step 4: Add the lifespan to main.py.jinja**

Edit `src/framework_cli/template/src/{{package_name}}/main.py.jinja`. The full file becomes (note the two new imports at top, the `lifespan` function, and `lifespan=lifespan` on `FastAPI(...)`):

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from {{ package_name }}.config.settings import Settings, get_settings
from {{ package_name }}.logging_config import configure_logging, get_logger
from {{ package_name }}.middleware.errors import register_exception_handlers
from {{ package_name }}.middleware.observability import ObservabilityMiddleware
from {{ package_name }}.observability.metrics import MetricsRegistry
from {{ package_name }}.observability.tracing import configure_tracing
from {{ package_name }}.routes import health, items


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hooks. On SIGTERM, uvicorn triggers shutdown — we close DB connections.

    Migrations + seed run in the container entrypoint before uvicorn starts, so startup here
    just logs; it must not require the DB to be reachable.
    """
    log = get_logger()
    log.info("startup", service=app.state.settings.service_name)
    yield
    from {{ package_name }}.db.engine import dispose_engine

    dispose_engine()
    log.info("graceful_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.resolved_log_level)

    app = FastAPI(title=settings.service_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.metrics = MetricsRegistry()
    app.add_middleware(ObservabilityMiddleware, metrics=app.state.metrics)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(items.router)
    configure_tracing(app, settings)
    return app


app = create_app()
```

> **Why import `dispose_engine` inside the shutdown branch:** it lets the test monkeypatch `{{ package_name }}.db.engine.dispose_engine` and have the lifespan pick up the patched attribute at call time. It also keeps `main` import-light. `app.state.settings` is set in `create_app` before the server starts, so it is available when lifespan startup runs.

- [ ] **Step 5: Run the test + the existing app tests**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && uv run pytest tests/functional/test_graceful_shutdown.py tests/functional/test_health.py tests/functional/test_error_handling.py -q`
Expected: PASS (existing tests that build `TestClient(create_app())` *without* `with` do not trigger lifespan, so they never dispose the real engine).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/src src/framework_cli/template/tests/functional/test_graceful_shutdown.py.jinja
git commit -m "feat(template): graceful shutdown lifespan disposes DB engine on SIGTERM"
```

---

## Task 6: Dev-intelligence note (CLAUDE.md) + framework render assertion

**Files:**
- Modify: `src/framework_cli/template/CLAUDE.md.jinja`
- Modify: `tests/test_copier_runner.py` (framework source test)

- [ ] **Step 1: Write the failing framework render test**

In `tests/test_copier_runner.py`, add this test (e.g., after `test_render_wires_items_route`):

```python
def test_render_includes_resilience_scaffold(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    src = dest / "src" / "demo"

    assert (src / "middleware" / "errors.py").is_file()
    assert (src / "resilience" / "retry.py").is_file()
    assert (src / "resilience" / "circuit_breaker.py").is_file()
    assert (src / "observability" / "recoverability.py").is_file()

    errors = (src / "middleware" / "errors.py").read_text()
    assert "application/problem+json" in errors

    main = (src / "main.py").read_text()
    assert "register_exception_handlers" in main
    assert "lifespan" in main

    pyproject = (dest / "pyproject.toml").read_text()
    assert "tenacity" in pyproject
    assert "pybreaker" in pyproject

    claude = (dest / "CLAUDE.md").read_text()
    assert "RFC 7807" in claude
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_resilience_scaffold -q`
Expected: FAIL on the `CLAUDE.md` assertion (`"RFC 7807" in claude`) — the rest already exist from Tasks 1–5; the doc note is the missing piece.

- [ ] **Step 3: Add the managed-block note to CLAUDE.md.jinja**

In `src/framework_cli/template/CLAUDE.md.jinja`, inside the `<!-- FRAMEWORK:BEGIN -->` … `<!-- FRAMEWORK:END -->` block, after the `## Conventions` list and before `## Quality commands`, insert:

```markdown
## Error handling & recoverability

Every service ships error-handling and recovery scaffolds — extend them, do not recreate them:

- A global exception handler returns RFC 7807 `application/problem+json` with the request correlation id (`middleware/errors.py`). Add new error cases there or raise `HTTPException` — both render consistently.
- `with_retry(...)` (`resilience/retry.py`) wraps flaky calls with `tenacity` backoff + jitter and records retry metrics.
- `build_breaker(...)` (`resilience/circuit_breaker.py`) wraps an unstable dependency with a `pybreaker` circuit breaker; its state is exposed on `/metrics`.
- Recovery paths are part of outcome-space mapping: test the failure *and* the recovery, not just the happy path.
```

- [ ] **Step 4: Run the render test to confirm it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_resilience_scaffold -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/CLAUDE.md.jinja tests/test_copier_runner.py
git commit -m "docs(template): document resilience scaffold in CLAUDE.md; render assertion"
```

---

## Task 7: Full verification + roadmap/state update

**Files:**
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md`
- Modify: `CLAUDE.md` (Current State pointer)

- [ ] **Step 1: Framework Layer-A gate (no Docker)**

Run from the repo root:
```bash
uv run ruff check .
uv run mypy src
uv run pytest tests/test_copier_runner.py tests/test_cli.py tests/test_naming.py tests/test_smoke.py -q
uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_precommit_runs_clean" -q
```
Expected: all PASS. The `precommit_runs_clean` test proves the generated `errors.py`, `retry.py`, `circuit_breaker.py`, `recoverability.py`, and the new tests are `ruff`-check, `ruff`-format, and `mypy` clean in a fresh project (it runs with `SKIP=coverage-threshold`, which needs Docker).

> If `ruff format` would change any new file, fix it now: `cd /tmp/demo && uv run ruff format --check .` mirrors what the hook enforces. The plan's code is pre-formatted, but verify after rendering.

- [ ] **Step 2: Generated-project full suite + coverage gate (needs Docker)**

```bash
uv run pytest \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_passes_its_own_tests" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_coverage_gate_passes" -q
```
Expected: PASS. The generated suite now includes the new unit + functional tests; coverage stays ≥ 70% (the new modules are well covered by Tasks 1–5). If Docker is unavailable, these skip — note that in the final review and rely on CI (Plan 5) to run them; the no-Docker `precommit_runs_clean` still gates cleanliness.

- [ ] **Step 3: (Optional, Docker) live-stack sanity**

The new code does not change the Compose stack, but graceful shutdown affects container stop. Optionally confirm the dev-lite stack still serves health and stops cleanly:
```bash
uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_dev_lite_stack_serves_health" -q
```
Expected: PASS.

- [ ] **Step 4: Update the meta-plan status table**

In `docs/superpowers/plans/2026-05-20-meta-plan.md`, change the Plan 4 row's status from `⬜ Not started` / `—` to `✅ Done` with this plan's filename and the merge commit (fill the commit after merge). Update the prose "Done so far" paragraph to mention the error-handling & recoverability scaffold.

- [ ] **Step 5: Update CLAUDE.md Current State pointer**

In `CLAUDE.md`, update **Last updated** (datetime + timezone), the **Where we are** line (Plan 4 merged), and **Next** (Plan 5 — CI/CD). Stage `CLAUDE.md` (the pre-commit hook blocks the commit otherwise).

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md
git commit -m "docs: mark Plan 4 (error handling & recoverability) complete"
```

---

## Self-Review

**Spec coverage (§19 + §8):**
- Global exception handler (RFC 7807, logs with context + correlation id) → Task 2. ✅
- Retry decorator (tenacity, backoff + jitter, logs each attempt) → Task 3. ✅
- Circuit breaker (pybreaker, state via `/metrics`, transitions logged) → Task 4. ✅
- Graceful shutdown (SIGTERM, close DB connections) → Task 5. ✅
- Dead letter queue → **deferred to Plan 8** (no workers yet) — documented in Scope & Non-Goals. ✅ (intentional gap)
- Recoverability metrics first-class (error counts, retry counts/success, circuit-breaker state) → Tasks 1–4, on `/metrics`. ✅ MTTR / graceful-degradation-events and `recovery_rate_pct`-as-SLO → deferred with rationale. ✅ (intentional gap)
- CLAUDE.md convention "recovery paths are part of outcome space mapping; no bare except" → Task 6 reinforces; the existing "no bare except" line is unchanged. ✅

**Placeholder scan:** No TBD/“add error handling”/“similar to Task N”. Every code step shows full code; every run step shows the command + expected result. ✅

**Type/name consistency across tasks:**
- `recoverability` singleton + methods (`record_unhandled_exception`, `record_retry_attempt`, `record_retry_recovered`, `record_retry_exhausted`, `set_circuit_state`, `circuit_state`, `snapshot`, `render_prometheus`, `reset`) — defined in Task 1; used identically in Tasks 2 (`record_unhandled_exception`), 3 (`record_retry_*`), 4 (`set_circuit_state`/`circuit_state`), and the autouse `reset`. ✅
- `snapshot()` keys (`unhandled`, `retry_attempts`, `retries_recovered`, `retries_exhausted`) match between Task 1's impl and the assertions in Tasks 1 & 3. ✅
- `register_exception_handlers(app)` — defined Task 2, called in `main.py.jinja` Task 2 & shown again in the full file in Task 5 (consistent). ✅
- `with_retry(*, max_attempts, initial_wait, max_wait, exceptions)` — signature in Task 3 matches the test's `with_retry(max_attempts=3, initial_wait=..., max_wait=..., exceptions=(KeyError,))`. ✅
- `build_breaker(*, name, fail_max, reset_timeout)` — keyword-only; Task 4 tests call it with keywords. ✅
- `dispose_engine()` — defined Task 5 in `db/engine.py`; monkeypatched by path `{{ package_name }}.db.engine.dispose_engine` and imported in the lifespan. ✅
- Prometheus metric names (`app_unhandled_exceptions_total`, `app_retry_attempts_total`, `app_retries_recovered_total`, `app_retries_exhausted_total`, `app_circuit_breaker_state{name=...}`) consistent between Task 1's render and Tasks 2 & 4's assertions. ✅

**Render correctness:** Files with `{{ package_name }}` imports get `.jinja` (the test files, `main`, `health`); pure-payload modules (`errors.py`, `retry.py`, `circuit_breaker.py`, `recoverability.py`) use relative imports (`from ..`), contain no Copier vars, and stay `.py` — matching the existing convention (`metrics.py`, `slo.py`, `observability.py` are plain `.py`). ✅

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-21-error-handling-recoverability.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration (matches this repo's established flow: branch → implementer per task → controller verification → Opus final review → merge to `master`).

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
