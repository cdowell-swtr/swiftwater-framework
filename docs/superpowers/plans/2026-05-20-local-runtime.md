# Local Runtime (Plan 3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the walking-skeleton stubs in generated projects with a real local runtime — `pydantic-settings` config, `structlog` + correlation IDs, an in-process metrics registry, a genuinely SLO-evaluating `/health`, and a Docker Compose + Traefik/mkcert HTTPS dev/test stack with healthcheck-based startup ordering and a `SERVICES.md`.

**Architecture:** Two phases. **Phase 1 (Tasks 1–6)** is pure Python and fully TDD'd with `pytest` — no Docker required. It adds `config/`, `observability/`, structured logging, an observability middleware, and rewrites the three monitoring endpoints to use real data. **Phase 2 (Tasks 7–11)** adds container infrastructure (`infra/docker/`, `infra/compose/`, `infra/traefik/`) plus Taskfile tasks; because it can't assume Docker is installed everywhere, it is validated two ways — *structural render tests* in the framework repo that parse the generated YAML/Dockerfile and assert correctness (always run), and a single *Docker-gated live acceptance test* that brings the stack up and curls `https://…/health` (skips when `docker` is absent, e.g. in CI and this sandbox).

**Tech Stack:** Python 3.12, FastAPI/Starlette, `pydantic-settings`, `structlog`, Uvicorn; Docker Compose (profiles), Traefik v3 (label-based routing + TLS), mkcert (local CA); Copier/Jinja; `uv`; `pytest` (+ `PyYAML` for the framework's render tests).

**Spec reference:** `docs/superpowers/specs/2026-05-20-framework-design.md` — §3 (template structure: `infra/`, `SERVICES.md`, `.env.example`), §8 (structured logging, correlation IDs, SLO `/health`, `/metrics`), §9 (Compose profiles, startup ordering, local HTTPS), §10 (settings via `pydantic-settings`), §15 (single-command startup, pre-flight, `SERVICES.md`).

**Scope boundaries (intentionally NOT in this plan):**
- The full **observability stack** (Prometheus/Grafana/Loki/Tempo/Alertmanager/OTEL) → **Plan 3b**. This plan exposes a real `/metrics` from the in-process registry and defines SLOs in code, which 3b scrapes/auto-provisions from. The `dev` profile here is **app + Traefik only**; `dev:lite` is app-only.
- **Database lifecycle** (PostgreSQL/SQLAlchemy/Alembic, migrate/seed, test DB) → **Plan 3c**. No DB service is added here.
- **Resilience scaffolds** (retry/circuit-breaker/DLQ, RFC 7807 handler) → **Plan 4**. The middleware here records a 5xx as an error for the error-rate SLO, but does not add recovery patterns.
- **CI / E2E / load** → **Plan 5**. The Compose `test` profile is seeded here but exercised by E2E later.

---

## Design Decisions (made per "decide & document")

1. **SLO definitions live in code as typed config** (`observability/slo.py`): a frozen `SLO` dataclass (`key`, `description`, `threshold`, `unit`, `warning_ratio`). `evaluate()` is a **pure function** taking SLOs + a `current_values` dict, returning the structured report — so it unit-tests trivially. `build_health_report()` gathers `current_values` from the metrics registry and calls `evaluate()`. 3b reads these same definitions to auto-generate dashboards/alerts.
2. **`/health` returns HTTP 200 with the SLO report** regardless of SLO status (it is a *report*, parsed by monitors/deploy validation, per §8). Liveness is `/heartbeat`. Per-SLO status is `ok` / `warning` / `breached`; overall `status` is `ok` if all ok else `degraded` (matches the spec's example body).
3. **Real metrics come from an in-process registry** (`observability/metrics.py`) fed by the middleware (request count, 5xx count, latency samples → p99). Monitoring endpoints (`/health`, `/metrics`, `/heartbeat`) are **not** recorded, so synthetic tests control the numbers and monitoring traffic doesn't skew SLOs.
4. **Compose/HTTPS validated without assuming Docker:** the framework's `tests/test_copier_runner.py` parses the generated `infra/compose/*.yml` with `PyYAML` and asserts structure (services, `profiles`, healthchecks, `depends_on: condition: service_healthy`, `TZ=UTC`, Traefik labels); a Dockerfile structural check asserts multi-stage. A single `@pytest.mark.skipif(shutil.which("docker") is None)` acceptance test brings the stack up and curls `https://…/health`. CI and this sandbox skip it; a dev box with Docker runs it.
5. **mkcert is detected, not silently installed.** Auto-installing a binary and writing a system trust root without consent is too invasive for a scaffold. The `task dev` pre-flight *detects* mkcert and fails with an OS-specific install hint if missing; `task certs` runs `mkcert -install` + issues `localhost`/`*.localhost` certs into `infra/traefik/certs/` (gitignored). Documented deviation from §15's "installs if absent."
6. **No new Copier questions** (YAGNI): the existing `project_name`/`project_slug`/`package_name`/`python_version` answers are sufficient. Service hostnames derive from `project_slug`.

---

## File Structure

Template additions/edits under `src/framework_cli/template/` (the generated-project payload):

```
src/framework_cli/template/
  pyproject.toml.jinja                      # EDIT: add pydantic-settings, structlog deps
  Taskfile.yml.jinja                        # EDIT: add dev / dev:lite / dev:reset / test:stack / certs (+ pre-flight)
  README.md.jinja                           # EDIT: document task dev, HTTPS, SERVICES.md
  .gitignore                                # EDIT: ignore infra/traefik/certs/*.pem
  .env.example                              # NEW: documented env vars (names only)
  SERVICES.md.jinja                         # NEW: internal + external service addresses
  src/{{package_name}}/
    main.py.jinja                           # EDIT: wire settings, logging, middleware, metrics
    config/
      __init__.py                           # NEW (empty)
      settings.py.jinja                     # NEW: pydantic-settings Settings + get_settings()
    observability/
      __init__.py                           # NEW (empty)
      metrics.py                            # NEW: in-process MetricsRegistry
      slo.py                                # NEW: SLO dataclass, default_slos, evaluate, build_health_report
    logging_config.py                       # NEW: structlog config + correlation_id contextvar
    middleware/
      __init__.py                           # NEW (empty)
      observability.py                      # NEW: ObservabilityMiddleware
    routes/
      health.py.jinja                       # EDIT: real /health and /metrics
  tests/
    unit/
      test_settings.py.jinja                # NEW
      test_metrics.py                       # NEW
      test_slo.py                           # NEW
      test_logging.py.jinja                 # NEW
    functional/
      __init__.py                           # NEW (empty)
      test_health.py.jinja                  # NEW (moved/expanded from unit/test_health.py)
      test_correlation_id.py.jinja          # NEW
  tests/unit/test_health.py.jinja           # DELETE (replaced by functional/test_health.py.jinja)
  infra/
    docker/
      Dockerfile                            # NEW: multi-stage uv build
    compose/
      base.yml.jinja                        # NEW: app service (build, TZ=UTC, healthcheck, traefik labels)
      dev.yml.jinja                         # NEW: dev profile (app hot-reload + traefik) ; dev:lite app-only
      test.yml.jinja                        # NEW: test profile (app, APP_ENVIRONMENT=test)
    traefik/
      traefik.yml                           # NEW: static config (entrypoints, providers, tls)
      dynamic/tls.yml                        # NEW: dynamic TLS (cert file paths)
      certs/.gitkeep                        # NEW (certs themselves gitignored)
```

Framework-repo edits (the framework's own tests/deps):

```
pyproject.toml                              # EDIT: add PyYAML to dev deps (render tests parse YAML)
tests/test_copier_runner.py                 # EDIT: render assertions for all new files
tests/acceptance/test_rendered_project.py   # EDIT: Docker-gated live-stack test
docs/superpowers/plans/2026-05-20-meta-plan.md  # EDIT (Task 11): mark 3a planned/done
```

**Responsibilities:** `config/settings.py` owns all configuration (nothing hardcoded). `observability/metrics.py` owns measurement; `observability/slo.py` owns SLO definitions + evaluation (pure). `logging_config.py` owns log setup + the correlation-id contextvar. `middleware/observability.py` is the single seam that ties a request to a correlation id, a timing sample, a metric, and a log line. `routes/health.py` only *reads* from these. The `infra/` tree is declarative and validated structurally.

---

# Phase 1 — Application runtime (pure Python, TDD)

## Task 1: Settings via pydantic-settings

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Create: `src/framework_cli/template/src/{{package_name}}/config/__init__.py`
- Create: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja`
- Test: `src/framework_cli/template/tests/unit/test_settings.py.jinja`

- [ ] **Step 1: Add runtime deps to the template `pyproject.toml.jinja`**

In `src/framework_cli/template/pyproject.toml.jinja`, change the `[project]` `dependencies` list to:

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.32",
    "pydantic-settings>=2.6",
]
```

> `structlog` is added in Task 4, where it is first imported (kept out of Task 1 so each commit's deps match its usage).

```toml
```

- [ ] **Step 2: Create the empty config package init**

Create `src/framework_cli/template/src/{{package_name}}/config/__init__.py` as an empty file.

- [ ] **Step 3: Write the failing test**

Create `src/framework_cli/template/tests/unit/test_settings.py.jinja`:

```python
import pytest

from {{ package_name }}.config.settings import Settings, get_settings


def test_defaults():
    s = Settings()
    assert s.environment == "dev"
    assert s.service_name == "{{ package_name }}"
    assert s.slo_request_latency_p99_ms == 200.0
    assert s.slo_error_rate_pct == 1.0


def test_resolved_log_level_is_debug_in_dev():
    assert Settings(environment="dev").resolved_log_level == "DEBUG"


@pytest.mark.parametrize("env", ["staging", "prod", "ci"])
def test_resolved_log_level_is_info_outside_dev(env):
    assert Settings(environment=env).resolved_log_level == "INFO"


def test_explicit_log_level_overrides_resolution():
    assert Settings(environment="prod", log_level="DEBUG").resolved_log_level == "DEBUG"


def test_env_vars_override(monkeypatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "prod")
    monkeypatch.setenv("APP_SLO_ERROR_RATE_PCT", "2.5")
    s = Settings()
    assert s.environment == "prod"
    assert s.slo_error_rate_pct == 2.5


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_settings.py -q` (inside a rendered project) — or rely on the framework acceptance test in Task 6.
Expected: FAIL — `ModuleNotFoundError: No module named '<pkg>.config.settings'`.

- [ ] **Step 5: Implement settings**

Create `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration, sourced from environment / .env. Never hardcode config."""

    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", extra="ignore"
    )

    environment: str = "dev"
    service_name: str = "{{ package_name }}"
    log_level: str | None = None  # explicit override; otherwise derived from environment

    # SLO thresholds (see observability/slo.py).
    slo_request_latency_p99_ms: float = 200.0
    slo_error_rate_pct: float = 1.0

    @property
    def resolved_log_level(self) -> str:
        if self.log_level is not None:
            return self.log_level.upper()
        return "DEBUG" if self.environment == "dev" else "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_settings.py -q` (rendered project).
Expected: PASS — all six tests.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/pyproject.toml.jinja \
        "src/framework_cli/template/src/{{package_name}}/config/__init__.py" \
        "src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja" \
        "src/framework_cli/template/tests/unit/test_settings.py.jinja"
git commit -m "feat(template): pydantic-settings config for generated projects"
```

---

## Task 2: In-process metrics registry

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/observability/__init__.py`
- Create: `src/framework_cli/template/src/{{package_name}}/observability/metrics.py`
- Test: `src/framework_cli/template/tests/unit/test_metrics.py.jinja`

> Note: `metrics.py` has no interpolation, so it is a **static** `.py` copied verbatim. Any test that imports the generated package must be a **`.jinja`** template so `{{ package_name }}` resolves — hence `test_metrics.py.jinja`.

- [ ] **Step 1: Create the empty observability package init**

Create `src/framework_cli/template/src/{{package_name}}/observability/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test**

Create `src/framework_cli/template/tests/unit/test_metrics.py.jinja`:

```python
from {{ package_name }}.observability.metrics import MetricsRegistry


def test_empty_registry_reports_zero():
    m = MetricsRegistry()
    assert m.total_requests == 0
    assert m.error_rate_pct() == 0.0
    assert m.p99_latency_ms() == 0.0


def test_records_requests_and_errors():
    m = MetricsRegistry()
    m.record_request(10.0, 200)
    m.record_request(20.0, 500)
    assert m.total_requests == 2
    assert m.error_rate_pct() == 50.0


def test_p99_latency():
    m = MetricsRegistry()
    for i in range(1, 101):  # 1..100 ms
        m.record_request(float(i), 200)
    assert m.p99_latency_ms() == 99.0


def test_render_prometheus_exposition():
    m = MetricsRegistry()
    m.record_request(15.0, 200)
    text = m.render_prometheus()
    assert "# TYPE app_requests_total counter" in text
    assert "app_requests_total 1\n" in text
    assert "app_request_latency_p99_ms 15.0\n" in text
    assert "app_up 1\n" in text


def test_reset_clears_all_state():
    m = MetricsRegistry()
    m.record_request(5.0, 500)
    m.reset()
    assert m.total_requests == 0
    assert m.p99_latency_ms() == 0.0
    assert m.error_rate_pct() == 0.0
```

> Reminder: any test file importing the generated package is a `.jinja` template so `{{ package_name }}` resolves — applies to the `test_slo` and `test_logging` files below too.

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_metrics.py -q` (rendered project).
Expected: FAIL — `ModuleNotFoundError: …observability.metrics`.

- [ ] **Step 4: Implement the registry**

Create `src/framework_cli/template/src/{{package_name}}/observability/metrics.py` (static, no Jinja):

```python
"""In-process metrics registry. Fed by the observability middleware; read by /metrics and /health.

A deliberately small, dependency-free store. The latency list is unbounded — fine for Plan 3a's
local runtime; Plan 3b should cap or flush it for high-traffic services. Plan 3b scrapes /metrics
into Prometheus.
"""

from __future__ import annotations

import math
import threading

_PROM_TEMPLATE = (
    "# HELP app_requests_total Total HTTP requests handled\n"
    "# TYPE app_requests_total counter\n"
    "app_requests_total {requests}\n"
    "# HELP app_request_errors_total Total 5xx responses\n"
    "# TYPE app_request_errors_total counter\n"
    "app_request_errors_total {errors}\n"
    "# HELP app_request_latency_p99_ms p99 request latency in milliseconds\n"
    "# TYPE app_request_latency_p99_ms gauge\n"
    "app_request_latency_p99_ms {p99}\n"
    "# HELP app_up Application up indicator\n"
    "# TYPE app_up gauge\n"
    "app_up 1\n"
)


def _p99(latencies: list[float]) -> float:
    """p99 of latencies (the max element for n < 100). Pure; safe to call while holding the lock."""
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    idx = math.ceil(0.99 * len(ordered)) - 1
    return ordered[max(0, idx)]


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latencies_ms: list[float] = []
        self._requests = 0
        self._errors = 0

    def record_request(self, latency_ms: float, status_code: int) -> None:
        with self._lock:
            self._requests += 1
            self._latencies_ms.append(latency_ms)
            if status_code >= 500:
                self._errors += 1

    @property
    def total_requests(self) -> int:
        with self._lock:
            return self._requests

    def error_rate_pct(self) -> float:
        with self._lock:
            if self._requests == 0:
                return 0.0
            return self._errors / self._requests * 100.0

    def p99_latency_ms(self) -> float:
        with self._lock:
            return _p99(self._latencies_ms)

    def render_prometheus(self) -> str:
        with self._lock:
            return _PROM_TEMPLATE.format(
                requests=self._requests,
                errors=self._errors,
                p99=_p99(self._latencies_ms),
            )

    def reset(self) -> None:
        with self._lock:
            self._latencies_ms.clear()
            self._requests = 0
            self._errors = 0
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_metrics.py -q` (rendered project).
Expected: PASS — all five tests (note `p99` of 1..100 with `ceil(0.99*100)-1 = 98` → `ordered[98] = 99.0`).

- [ ] **Step 6: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/observability/__init__.py" \
        "src/framework_cli/template/src/{{package_name}}/observability/metrics.py" \
        "src/framework_cli/template/tests/unit/test_metrics.py.jinja"
git commit -m "feat(template): in-process metrics registry"
```

---

## Task 3: SLO definitions + evaluation

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/observability/slo.py`
- Test: `src/framework_cli/template/tests/unit/test_slo.py.jinja`

- [ ] **Step 1: Write the failing test**

Create `src/framework_cli/template/tests/unit/test_slo.py.jinja`:

```python
from {{ package_name }}.config.settings import Settings
from {{ package_name }}.observability.metrics import MetricsRegistry
from {{ package_name }}.observability.slo import (
    build_health_report,
    default_slos,
    evaluate,
)


def test_default_slos_from_settings():
    slos = {s.key: s for s in default_slos(Settings())}
    assert slos["request_latency_p99_ms"].threshold == 200.0
    assert slos["error_rate_pct"].threshold == 1.0


def test_evaluate_ok_warning_breached():
    slos = default_slos(Settings())  # latency thr 200 (warn >=180), error thr 1.0 (warn >=0.9)
    report = evaluate(
        slos,
        {"request_latency_p99_ms": 50.0, "error_rate_pct": 0.95},
    )
    assert report["slos"]["request_latency_p99_ms"]["status"] == "ok"
    assert report["slos"]["error_rate_pct"]["status"] == "warning"
    assert report["status"] == "degraded"


def test_evaluate_breached_sets_degraded():
    slos = default_slos(Settings())
    report = evaluate(slos, {"request_latency_p99_ms": 340.0, "error_rate_pct": 0.0})
    assert report["slos"]["request_latency_p99_ms"]["status"] == "breached"
    assert report["status"] == "degraded"


def test_evaluate_all_ok():
    slos = default_slos(Settings())
    report = evaluate(slos, {"request_latency_p99_ms": 10.0, "error_rate_pct": 0.0})
    assert report["status"] == "ok"


def test_build_health_report_reads_metrics():
    m = MetricsRegistry()
    m.record_request(10.0, 200)
    report = build_health_report(m, Settings())
    assert report["status"] == "ok"
    assert set(report["slos"]) == {"request_latency_p99_ms", "error_rate_pct"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_slo.py -q` (rendered project).
Expected: FAIL — `ModuleNotFoundError: …observability.slo`.

- [ ] **Step 3: Implement SLOs**

Create `src/framework_cli/template/src/{{package_name}}/observability/slo.py` (static, no Jinja):

```python
"""SLO definitions and evaluation.

SLOs are typed config (single source of truth). `evaluate` is pure — it takes the SLOs
and a dict of current values and returns the structured /health report. Plan 3b reads
these same definitions to auto-generate dashboards and alert rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config.settings import Settings
    from .metrics import MetricsRegistry


@dataclass(frozen=True, slots=True)
class SLO:
    key: str
    description: str
    threshold: float
    unit: str
    warning_ratio: float = 0.9  # current >= warning_ratio * threshold -> "warning"


def default_slos(settings: "Settings") -> list[SLO]:
    return [
        SLO(
            key="request_latency_p99_ms",
            description="p99 request latency",
            threshold=settings.slo_request_latency_p99_ms,
            unit="ms",
        ),
        SLO(
            key="error_rate_pct",
            description="5xx error rate",
            threshold=settings.slo_error_rate_pct,
            unit="percent",
        ),
    ]


def _status_for(current: float, slo: SLO) -> str:
    if current > slo.threshold:
        return "breached"
    if current >= slo.warning_ratio * slo.threshold:
        return "warning"
    return "ok"


def evaluate(slos: list[SLO], current_values: dict[str, float]) -> dict:
    slo_report: dict[str, dict] = {}
    for slo in slos:
        current = current_values[slo.key]
        slo_report[slo.key] = {
            "threshold": slo.threshold,
            "current": current,
            "unit": slo.unit,
            "status": _status_for(current, slo),
        }
    overall = "ok" if all(s["status"] == "ok" for s in slo_report.values()) else "degraded"
    return {"status": overall, "slos": slo_report}


def build_health_report(metrics: "MetricsRegistry", settings: "Settings") -> dict:
    current_values = {
        "request_latency_p99_ms": metrics.p99_latency_ms(),
        "error_rate_pct": metrics.error_rate_pct(),
    }
    return evaluate(default_slos(settings), current_values)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_slo.py -q` (rendered project).
Expected: PASS — all five tests.

- [ ] **Step 5: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/observability/slo.py" \
        "src/framework_cli/template/tests/unit/test_slo.py.jinja"
git commit -m "feat(template): SLO definitions and pure evaluation"
```

---

## Task 4: Structured logging + correlation-id contextvar

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja` (add `structlog>=24.4` dep — deferred from Task 1)
- Create: `src/framework_cli/template/src/{{package_name}}/logging_config.py`
- Test: `src/framework_cli/template/tests/unit/test_logging.py.jinja`

- [ ] **Step 1: Write the failing test**

Create `src/framework_cli/template/tests/unit/test_logging.py.jinja`:

```python
import logging

import structlog

from {{ package_name }}.logging_config import (
    add_correlation_id,
    configure_logging,
    correlation_id_var,
    get_logger,
)


def test_add_correlation_id_injects_when_set():
    token = correlation_id_var.set("abc-123")
    try:
        event = add_correlation_id(None, "info", {"event": "hi"})
    finally:
        correlation_id_var.reset(token)
    assert event["correlation_id"] == "abc-123"


def test_add_correlation_id_omits_when_unset():
    event = add_correlation_id(None, "info", {"event": "hi"})
    assert "correlation_id" not in event


def test_configure_logging_sets_level():
    configure_logging("WARNING")
    # filtering bound logger drops INFO at WARNING level
    assert structlog.get_config()["wrapper_class"] == structlog.make_filtering_bound_logger(
        logging.WARNING
    )


def test_get_logger_is_usable():
    configure_logging("DEBUG")
    get_logger().info("smoke", key="value")  # must not raise
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_logging.py -q` (rendered project).
Expected: FAIL — `ModuleNotFoundError: …logging_config`.

- [ ] **Step 3: Implement logging config**

First add `"structlog>=24.4",` to the `[project]` `dependencies` in `pyproject.toml.jinja` (deferred from Task 1). Then create `src/framework_cli/template/src/{{package_name}}/logging_config.py` (static, no Jinja):

```python
"""structlog configuration and the request correlation-id contextvar.

A correlation id is generated at the request boundary (see middleware/observability.py)
and stored in this contextvar; `add_correlation_id` injects it into every log entry
emitted within that request's async context.
"""

from __future__ import annotations

import contextvars
import logging

import structlog

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def add_correlation_id(logger, method_name, event_dict):  # noqa: ANN001, ARG001
    cid = correlation_id_var.get()
    if cid is not None:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        cache_logger_on_first_use=True,
    )


def get_logger() -> structlog.stdlib.BoundLogger:
    return structlog.get_logger()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_logging.py -q` (rendered project).
Expected: PASS — all four tests.

- [ ] **Step 5: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/logging_config.py" \
        "src/framework_cli/template/tests/unit/test_logging.py.jinja"
git commit -m "feat(template): structlog config + correlation-id contextvar"
```

---

## Task 5: Observability middleware

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/middleware/__init__.py`
- Create: `src/framework_cli/template/src/{{package_name}}/middleware/observability.py`
- Test: covered by Task 6's functional tests (the middleware is only meaningful mounted on the app).

- [ ] **Step 1: Create the empty middleware package init**

Create `src/framework_cli/template/src/{{package_name}}/middleware/__init__.py` as an empty file.

- [ ] **Step 2: Implement the middleware**

Create `src/framework_cli/template/src/{{package_name}}/middleware/observability.py` (static, no Jinja):

```python
"""Per-request observability: correlation id, latency timing, metric recording, request log.

Monitoring endpoints (/health, /metrics, /heartbeat) are not recorded so synthetic load
controls the SLO inputs and monitoring traffic does not skew the SLOs.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ..logging_config import correlation_id_var, get_logger

if TYPE_CHECKING:
    from ..observability.metrics import MetricsRegistry

_UNRECORDED_PATHS = frozenset({"/health", "/metrics", "/heartbeat"})
_CORRELATION_HEADER = "X-Correlation-ID"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, metrics: "MetricsRegistry") -> None:
        super().__init__(app)
        self._metrics = metrics
        self._log = get_logger()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cid = request.headers.get(_CORRELATION_HEADER) or uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        start = time.perf_counter()
        record = request.url.path not in _UNRECORDED_PATHS
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if record:
                self._metrics.record_request(elapsed_ms, 500)
            self._log.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round(elapsed_ms, 2),
            )
            correlation_id_var.reset(token)
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if record:
            self._metrics.record_request(elapsed_ms, response.status_code)
        self._log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed_ms, 2),
        )
        response.headers[_CORRELATION_HEADER] = cid
        correlation_id_var.reset(token)
        return response
```

- [ ] **Step 3: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/middleware/__init__.py" \
        "src/framework_cli/template/src/{{package_name}}/middleware/observability.py"
git commit -m "feat(template): observability middleware (correlation id, timing, metrics)"
```

---

## Task 6: Wire the app + real /health and /metrics

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/main.py.jinja`
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja`
- Create: `src/framework_cli/template/tests/functional/__init__.py`
- Create: `src/framework_cli/template/tests/functional/test_health.py.jinja`
- Create: `src/framework_cli/template/tests/functional/test_correlation_id.py.jinja`
- Delete: `src/framework_cli/template/tests/unit/test_health.py.jinja`
- Modify (framework): `tests/test_copier_runner.py`

- [ ] **Step 1: Rewrite the health routes to use real data**

Replace `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja` with:

```python
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from {{ package_name }}.observability.slo import build_health_report

router = APIRouter()


@router.get("/heartbeat", response_class=PlainTextResponse)
def heartbeat() -> PlainTextResponse:
    """Liveness ping — the process is up. No dependency checks."""
    return PlainTextResponse("OK", status_code=200)


@router.get("/health")
def health(request: Request) -> JSONResponse:
    """Readiness + SLO status. Returns 200 with the structured SLO report."""
    report = build_health_report(request.app.state.metrics, request.app.state.settings)
    return JSONResponse(report, status_code=200)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request) -> PlainTextResponse:
    """Prometheus exposition format from the in-process registry."""
    return PlainTextResponse(
        request.app.state.metrics.render_prometheus(),
        status_code=200,
        media_type="text/plain; version=0.0.4",
    )
```

- [ ] **Step 2: Rewrite `main.py.jinja` to wire everything**

Replace `src/framework_cli/template/src/{{package_name}}/main.py.jinja` with:

```python
from fastapi import FastAPI

from {{ package_name }}.config.settings import Settings, get_settings
from {{ package_name }}.logging_config import configure_logging
from {{ package_name }}.middleware.observability import ObservabilityMiddleware
from {{ package_name }}.observability.metrics import MetricsRegistry
from {{ package_name }}.routes import health


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.resolved_log_level)

    app = FastAPI(title=settings.service_name)
    app.state.settings = settings
    app.state.metrics = MetricsRegistry()
    app.add_middleware(ObservabilityMiddleware, metrics=app.state.metrics)
    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 3: Write the failing functional tests**

Create `src/framework_cli/template/tests/functional/__init__.py` (empty).

Create `src/framework_cli/template/tests/functional/test_health.py.jinja`:

```python
from fastapi.testclient import TestClient

from {{ package_name }}.main import create_app


def make_client() -> TestClient:
    return TestClient(create_app())


def test_heartbeat_returns_ok():
    r = make_client().get("/heartbeat")
    assert r.status_code == 200
    assert r.text == "OK"


def test_health_returns_slo_report():
    r = make_client().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    assert "request_latency_p99_ms" in body["slos"]
    assert "error_rate_pct" in body["slos"]
    assert body["slos"]["error_rate_pct"]["threshold"] == 1.0


def test_health_reflects_recorded_errors():
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    # Drive a non-monitoring 5xx through the middleware so error_rate registers.
    app.state.metrics.record_request(10.0, 500)
    body = client.get("/health").json()
    assert body["slos"]["error_rate_pct"]["current"] == 100.0
    assert body["slos"]["error_rate_pct"]["status"] == "breached"
    assert body["status"] == "degraded"


def test_metrics_is_prometheus_text():
    r = make_client().get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "app_up 1" in r.text
    assert "app_requests_total" in r.text
```

Create `src/framework_cli/template/tests/functional/test_correlation_id.py.jinja`:

```python
from fastapi.testclient import TestClient

from {{ package_name }}.main import create_app

client = TestClient(create_app())


def test_response_has_correlation_id_header():
    r = client.get("/heartbeat")
    assert r.headers.get("X-Correlation-ID")


def test_inbound_correlation_id_is_echoed():
    r = client.get("/heartbeat", headers={"X-Correlation-ID": "trace-42"})
    assert r.headers["X-Correlation-ID"] == "trace-42"
```

- [ ] **Step 4: Delete the obsolete walking-skeleton test**

Delete `src/framework_cli/template/tests/unit/test_health.py.jinja` (its assertions are superseded by `tests/functional/test_health.py.jinja`).

- [ ] **Step 5: Update the framework render test**

In `tests/test_copier_runner.py`, add:

```python
def test_render_includes_runtime_modules(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert (dest / "src" / "demo" / "config" / "settings.py").is_file()
    assert (dest / "src" / "demo" / "observability" / "metrics.py").is_file()
    assert (dest / "src" / "demo" / "observability" / "slo.py").is_file()
    assert (dest / "src" / "demo" / "logging_config.py").is_file()
    assert (dest / "src" / "demo" / "middleware" / "observability.py").is_file()
    # health route now reads the real SLO report
    health = (dest / "src" / "demo" / "routes" / "health.py").read_text()
    assert "build_health_report" in health
```

- [ ] **Step 6: Run the rendered project's full suite via the framework acceptance test**

Run (from the framework repo): `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_passes_its_own_tests -q`
Expected: PASS — the rendered demo project's unit + functional suites (settings, metrics, slo, logging, health, correlation id) all pass. If `uv` is absent it SKIPS.

Also run: `uv run pytest tests/test_copier_runner.py -q` → PASS (incl. the new render assertion).

- [ ] **Step 7: Confirm the rendered project still passes its coverage gate and pre-commit**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -q`
Expected: PASS — `test_rendered_project_coverage_gate_passes` (new modules are all exercised by their tests, so coverage stays ≥70%) and `test_rendered_project_precommit_runs_clean` (the new template Python is ruff/ruff-format/mypy clean — keep it so).

- [ ] **Step 8: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/main.py.jinja" \
        "src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja" \
        "src/framework_cli/template/tests/functional/" \
        tests/test_copier_runner.py
git rm "src/framework_cli/template/tests/unit/test_health.py.jinja"
git commit -m "feat(template): real SLO /health and /metrics wired through middleware"
```

---

# Phase 2 — Container runtime (render-tested + Docker-gated)

> All Phase-2 files are **payload validated structurally**. Add `PyYAML` to the framework's own dev deps first so the render tests can parse Compose.

## Task 7: Multi-stage Dockerfile + PyYAML for render tests

**Files:**
- Modify: `pyproject.toml` (framework repo — add `pyyaml` dev dep)
- Create: `src/framework_cli/template/infra/docker/Dockerfile.jinja`
- Create: `src/framework_cli/template/.dockerignore` (build-context root)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Add PyYAML to the framework's dev deps**

In the framework repo `pyproject.toml`, `[dependency-groups]` `dev`, add `"pyyaml>=6.0"`. Then run `uv sync`.

- [ ] **Step 2: Write the failing render test**

In `tests/test_copier_runner.py` add:

```python
def test_render_includes_dockerfile_multistage(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    dockerfile = (dest / "infra" / "docker" / "Dockerfile")
    assert dockerfile.is_file()
    text = dockerfile.read_text()
    # multi-stage: a builder stage and a runtime stage
    assert text.count("FROM ") >= 2
    assert " AS builder" in text
    assert "uv sync" in text
    # a .dockerignore at the build-context root keeps the host .venv out of the image
    assert ".venv" in (dest / ".dockerignore").read_text()
```

Also create `src/framework_cli/template/.dockerignore` (static — at the **template/project root**, because Compose builds with `context: ../..`; Docker reads `.dockerignore` from the context root). Without it, the Dockerfile's `COPY . .` copies the host `.venv` over the builder-installed one — a real ABI/reproducibility bug:

```
# Keep the Docker build context lean and the host venv out of the image.
.venv/
.git/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
build/
*.egg-info/
.env
infra/traefik/certs/*.pem
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_dockerfile_multistage -q`
Expected: FAIL — `infra/docker/Dockerfile` does not exist.

- [ ] **Step 4: Create the Dockerfile**

Create `src/framework_cli/template/infra/docker/Dockerfile.jinja` (the `.jinja` suffix is only so the `CMD` package name interpolates; Copier renders it to `infra/docker/Dockerfile`):

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
ENV TZ=UTC PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /app /app
EXPOSE 8000
CMD ["uvicorn", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "{{ package_name }}.main:app"]
```

- [ ] **Step 5: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_dockerfile_multistage -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml "src/framework_cli/template/infra/docker/Dockerfile.jinja" tests/test_copier_runner.py
git commit -m "feat(template): multi-stage Dockerfile; pyyaml for render tests"
```

---

## Task 8: Compose base/dev/test profiles with healthcheck ordering

**Files:**
- Create: `src/framework_cli/template/infra/compose/base.yml.jinja`
- Create: `src/framework_cli/template/infra/compose/dev.yml.jinja`
- Create: `src/framework_cli/template/infra/compose/test.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

In `tests/test_copier_runner.py`, ensure `import yaml` is at the top, then add:

```python
def test_render_compose_structure(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    base = yaml.safe_load((dest / "infra" / "compose" / "base.yml").read_text())
    app = base["services"]["app"]
    assert app["environment"]["TZ"] == "UTC"
    assert "healthcheck" in app
    assert "/heartbeat" in " ".join(app["healthcheck"]["test"])
    # traefik routing label present, keyed on the project slug host
    labels = "\n".join(app["labels"])
    assert "traefik.enable=true" in labels
    assert "demo.localhost" in labels

    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    assert "dev" in dev["services"]["app"]["profiles"]
    assert any("8000" in str(p) for p in dev["services"]["app"]["ports"])
    traefik = dev["services"]["traefik"]
    assert traefik["depends_on"]["app"]["condition"] == "service_healthy"
    assert any(p for p in traefik["ports"] if "443" in str(p))

    test = yaml.safe_load((dest / "infra" / "compose" / "test.yml").read_text())
    assert test["services"]["app"]["environment"]["APP_ENVIRONMENT"] == "test"
    assert "test" in test["services"]["app"]["profiles"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_compose_structure -q`
Expected: FAIL — compose files do not exist.

- [ ] **Step 3: Create `base.yml.jinja`**

Create `src/framework_cli/template/infra/compose/base.yml.jinja`:

```yaml
# Base service definitions, shared by all profiles. Compose merges this with the
# profile overlay: `docker compose -f infra/compose/base.yml -f infra/compose/dev.yml ...`.
services:
  app:
    build:
      context: ../..
      dockerfile: infra/docker/Dockerfile
    environment:
      TZ: UTC
      APP_ENVIRONMENT: dev
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/heartbeat').status==200 else 1)"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 5s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.app.rule=Host(`{{ project_slug }}.localhost`)"
      - "traefik.http.routers.app.entrypoints=websecure"
      - "traefik.http.routers.app.tls=true"
      - "traefik.http.services.app.loadbalancer.server.port=8000"
```

- [ ] **Step 4: Create `dev.yml.jinja`**

Create `src/framework_cli/template/infra/compose/dev.yml.jinja`:

```yaml
# dev profile: app (hot reload) + Traefik HTTPS. `dev:lite` runs the app alone.
services:
  app:
    profiles: ["dev", "lite"]   # task name is `dev:lite`, but the Compose profile is `lite` (colons are invalid in profile names)
    command: ["uvicorn", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--reload", "{{ package_name }}.main:app"]
    ports:
      - "8000:8000"
    volumes:
      - ../../src:/app/src
    environment:
      WATCHFILES_FORCE_POLLING: "true"  # reliable reload on Windows/WSL bind mounts

  traefik:
    image: traefik:v3.1
    profiles: ["dev"]
    command:
      - "--configfile=/etc/traefik/traefik.yml"
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "../traefik/traefik.yml:/etc/traefik/traefik.yml:ro"
      - "../traefik/dynamic:/etc/traefik/dynamic:ro"
      - "../traefik/certs:/etc/traefik/certs:ro"
    depends_on:
      app:
        condition: service_healthy
```

- [ ] **Step 5: Create `test.yml.jinja`**

Create `src/framework_cli/template/infra/compose/test.yml.jinja`:

```yaml
# test profile: app with test config, no Traefik. Seed for the E2E stack (Plan 5).
services:
  app:
    profiles: ["test"]
    environment:
      APP_ENVIRONMENT: test
```

- [ ] **Step 6: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_compose_structure -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add "src/framework_cli/template/infra/compose/" tests/test_copier_runner.py
git commit -m "feat(template): compose base/dev/test profiles with healthcheck ordering"
```

---

## Task 9: Traefik static/dynamic config + mkcert cert dir

**Files:**
- Create: `src/framework_cli/template/infra/traefik/traefik.yml`
- Create: `src/framework_cli/template/infra/traefik/dynamic/tls.yml`
- Create: `src/framework_cli/template/infra/traefik/certs/.gitkeep`
- Modify: `src/framework_cli/template/.gitignore`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

In `tests/test_copier_runner.py` add:

```python
def test_render_traefik_and_certs_gitignored(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    static = yaml.safe_load((dest / "infra" / "traefik" / "traefik.yml").read_text())
    assert "websecure" in static["entryPoints"]
    assert static["providers"]["docker"]["exposedByDefault"] is False

    tls = yaml.safe_load((dest / "infra" / "traefik" / "dynamic" / "tls.yml").read_text())
    certs = tls["tls"]["certificates"][0]
    assert certs["certFile"].endswith(".pem")

    assert (dest / "infra" / "traefik" / "certs" / ".gitkeep").is_file()
    gitignore = (dest / ".gitignore").read_text()
    assert "infra/traefik/certs/*.pem" in gitignore
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_traefik_and_certs_gitignored -q`
Expected: FAIL — traefik files do not exist.

- [ ] **Step 3: Create the Traefik static config**

Create `src/framework_cli/template/infra/traefik/traefik.yml` (static, no Jinja):

```yaml
entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

providers:
  docker:
    exposedByDefault: false
  file:
    directory: /etc/traefik/dynamic
    watch: true

log:
  level: INFO
```

- [ ] **Step 4: Create the dynamic TLS config**

Create `src/framework_cli/template/infra/traefik/dynamic/tls.yml` (static, no Jinja):

```yaml
tls:
  certificates:
    - certFile: /etc/traefik/certs/localhost.pem
      keyFile: /etc/traefik/certs/localhost-key.pem
  stores:
    default:
      defaultCertificate:
        certFile: /etc/traefik/certs/localhost.pem
        keyFile: /etc/traefik/certs/localhost-key.pem
```

- [ ] **Step 5: Create the certs dir placeholder**

Create `src/framework_cli/template/infra/traefik/certs/.gitkeep` (empty file).

- [ ] **Step 6: Ignore generated certs**

In `src/framework_cli/template/.gitignore`, append:

```
# Local mkcert certificates (generated by `task certs`)
infra/traefik/certs/*.pem
```

- [ ] **Step 7: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_traefik_and_certs_gitignored -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add "src/framework_cli/template/infra/traefik/" "src/framework_cli/template/.gitignore" tests/test_copier_runner.py
git commit -m "feat(template): traefik HTTPS config + gitignored mkcert certs"
```

---

## Task 10: `.env.example`, `SERVICES.md`, Taskfile tasks, README

**Files:**
- Create: `src/framework_cli/template/.env.example`
- Create: `src/framework_cli/template/SERVICES.md.jinja`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Modify: `src/framework_cli/template/README.md.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

In `tests/test_copier_runner.py` add:

```python
def test_render_env_services_and_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    env = (dest / ".env.example").read_text()
    assert "APP_ENVIRONMENT=" in env
    assert "APP_SLO_REQUEST_LATENCY_P99_MS=" in env

    services = (dest / "SERVICES.md").read_text()
    assert "demo.localhost" in services      # external HTTPS host
    assert "app:8000" in services             # internal docker address

    taskfile = (dest / "Taskfile.yml").read_text()
    for task in ("dev:", "dev:lite:", "dev:reset:", "certs:", "test:stack:"):
        assert task in taskfile
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_env_services_and_tasks -q`
Expected: FAIL — `.env.example` does not exist.

- [ ] **Step 3: Create `.env.example`**

Create `src/framework_cli/template/.env.example` (static, no Jinja — names + descriptions only, no secrets):

```bash
# Copy to .env (gitignored) and adjust. All vars are read via config/settings.py.
# Application environment: dev | test | staging | prod (drives log level + config).
APP_ENVIRONMENT=dev
# Optional explicit log level (DEBUG/INFO/WARNING/ERROR). Unset = derived from APP_ENVIRONMENT.
# APP_LOG_LEVEL=
# SLO thresholds (drive /health evaluation and, in Plan 3b, dashboards + alerts).
APP_SLO_REQUEST_LATENCY_P99_MS=200
APP_SLO_ERROR_RATE_PCT=1.0
```

- [ ] **Step 4: Create `SERVICES.md.jinja`**

Create `src/framework_cli/template/SERVICES.md.jinja`:

```markdown
# Services

Internal address = Docker network hostname (service-to-service calls).
External address = host browser access (HTTPS via Traefik + mkcert).

| Service | Internal address | External address | Notes |
|---------|------------------|------------------|-------|
| app     | `app:8000`       | `https://{{ project_slug }}.localhost` | FastAPI app; `/heartbeat`, `/health`, `/metrics` |
| traefik | `traefik:80/443` | `https://{{ project_slug }}.localhost` | Reverse proxy, TLS termination (dev profile) |

Run `task certs` once to generate the local mkcert certificate, then `task dev`.
```

- [ ] **Step 5: Extend `Taskfile.yml.jinja`**

In `src/framework_cli/template/Taskfile.yml.jinja`, keep the existing `dev`, `test`, `test:cov`, `hooks`, `hooks:run`, `lint` tasks, and **replace the existing `dev` task** plus add the stack tasks. The new/changed tasks (note: no Go-template expressions, so no `{% raw %}` needed):

```yaml
  dev:
    desc: Full local stack over HTTPS (app + Traefik). Requires Docker + mkcert.
    preconditions:
      - sh: command -v docker
        msg: "Docker is required for `task dev`. Install Docker, then retry."
      - sh: test -f infra/traefik/certs/localhost.pem
        msg: "No local certs. Run `task certs` first (installs mkcert CA + issues localhost certs)."
    cmds:
      - docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile dev up --build

  dev:lite:
    desc: App only over plain HTTP at localhost:8000 (no Traefik) — resource-light.
    preconditions:
      - sh: command -v docker
        msg: "Docker is required for `task dev:lite`."
    cmds:
      - docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite up --build

  dev:reset:
    desc: Tear the local stack down (including volumes) and rebuild.
    preconditions:
      - sh: command -v docker
        msg: "Docker is required for `task dev:reset`."
    cmds:
      - docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile dev down -v
      - task: dev

  test:stack:
    desc: Bring up the test-profile stack (app with APP_ENVIRONMENT=test).
    preconditions:
      - sh: command -v docker
        msg: "Docker is required for `task test:stack`."
    cmds:
      - docker compose -f infra/compose/base.yml -f infra/compose/test.yml --profile test up --build

  certs:
    desc: Install the mkcert local CA and issue localhost certificates for Traefik.
    preconditions:
      - sh: command -v mkcert
        msg: "mkcert is required. Install it (https://github.com/FiloSottile/mkcert#installation), then retry."
    cmds:
      - mkcert -install
      - mkcert -cert-file infra/traefik/certs/localhost.pem -key-file infra/traefik/certs/localhost-key.pem localhost "*.localhost" 127.0.0.1 ::1
```

> The existing `test:` task (local `uv run pytest -q`) stays unchanged — it is the fast unit/functional run. `test:stack` is the containerised profile.

- [ ] **Step 6: Update the README**

In `src/framework_cli/template/README.md.jinja`, under `## Quickstart`, add the stack commands (keep the nested fence style):

```markdown
## Local stack (HTTPS)

```bash
task certs     # one-time: install mkcert CA + issue localhost certs
task dev       # full stack at https://{{ project_slug }}.localhost (app + Traefik)
task dev:lite  # app only at http://localhost:8000 (no Traefik)
```

Service addresses are documented in `SERVICES.md`.
```

- [ ] **Step 7: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_env_services_and_tasks -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add "src/framework_cli/template/.env.example" \
        "src/framework_cli/template/SERVICES.md.jinja" \
        "src/framework_cli/template/Taskfile.yml.jinja" \
        "src/framework_cli/template/README.md.jinja" \
        tests/test_copier_runner.py
git commit -m "feat(template): .env.example, SERVICES.md, stack Taskfile tasks, README"
```

---

## Task 11: Docker-gated live-stack acceptance test + meta-plan update

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md`

- [ ] **Step 1: Add the Docker-gated live test**

In `tests/acceptance/test_rendered_project.py` add (it mirrors the existing `skipif uv is None` style, and additionally skips when Docker is absent — so CI and sandboxes skip it, a dev box with Docker runs it):

```python
import time
import urllib.request


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("docker") is None,
    reason="uv and docker are required for the live-stack test",
)
def test_rendered_project_dev_lite_stack_serves_health(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base = "infra/compose/base.yml"
    dev = "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # app is published on 8000 in dev:lite (no Traefik)
        deadline = time.time() + 90
        body = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read())
                        break
            except OSError:
                time.sleep(2)
        assert body is not None, "app did not serve /health within 90s"
        assert body["status"] in {"ok", "degraded"}
        assert "request_latency_p99_ms" in body["slos"]
    finally:
        subprocess.run(down, cwd=dest)
```

> For `dev:lite` to publish port 8000 on the host, add to `infra/compose/dev.yml.jinja` under the `app` service (Task 8 follow-up): `ports: ["8000:8000"]`. Add this in Task 8 if not already present; the live test depends on it. (Re-run Task 8's render test after — it still passes; the new key is additive.)

- [ ] **Step 2: Run the acceptance suite**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -q`
Expected: existing tests PASS; the new live-stack test **SKIPS** here (no Docker) and **RUNS** on a Docker-equipped dev box. Where it runs, it brings up the app, polls `/health`, and asserts the SLO report.

- [ ] **Step 3: Run the full framework gate**

Run: `uv run pytest -q` → all pass (skips noted).
Run: `uv run ruff check .` → clean. Run: `uv run mypy src` → clean (template dir is excluded; framework source unchanged).

- [ ] **Step 4: Update the meta-plan + CLAUDE.md Current State**

In `docs/superpowers/plans/2026-05-20-meta-plan.md`: change the Plan 3 row to reflect 3a landed (e.g. add a `3a` row marked ✅ with this plan's filename and the merge commit), and adjust the "Done so far" / "Next" notes to point at 3b. In `CLAUDE.md`, update the **Current State** pointer per the repo's commit-state convention (and stage `CLAUDE.md`).

- [ ] **Step 5: Commit**

```bash
git add tests/acceptance/test_rendered_project.py \
        "src/framework_cli/template/infra/compose/dev.yml.jinja" \
        docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md
git commit -m "test(template): docker-gated live-stack health check; mark plan 3a done"
```

---

## Self-Review

**1. Spec coverage (Plan 3a subset):**
- §10 settings via `pydantic-settings`, no hardcoded config → Task 1 ✓
- §8 structured logging (`structlog`) + correlation IDs propagated through async context → Tasks 4, 5 ✓
- §8 real SLO-evaluating `/health` (structured JSON, per-SLO status), `/metrics` (Prometheus exposition) → Tasks 2, 3, 6 ✓
- §3 template structure: `infra/docker`, `infra/compose`, `infra/traefik`, `.env.example`, `SERVICES.md` → Tasks 7–10 ✓
- §9 Compose profiles (`dev`/`dev:lite`/`test`), healthchecks + `depends_on: condition: service_healthy`, `TZ=UTC`, local HTTPS via Traefik+mkcert, file-watch polling on Windows → Tasks 8–10 ✓
- §15 single-command `task dev`, pre-flight checks, `SERVICES.md`, `task certs`/`dev:reset` → Task 10 ✓
- **Deliberately deferred** (stated in Scope boundaries, not gaps): observability stack (3b), database (3c), resilience/RFC-7807 (4), CI/E2E/load (5). The `base.yml` Compose profile structure and SLO-in-code are the seams 3b/3c extend.

**2. Placeholder scan:** No "TBD"/"handle appropriately". Each code step shows complete, final content — every code block is the version to implement (no "do X not Y" detours).

**3. Type/consistency check:** Names are consistent across tasks — `Settings`/`get_settings`/`resolved_log_level` (Task 1) used in 3, 4, 6; `MetricsRegistry` methods `record_request`/`total_requests`/`error_rate_pct`/`p99_latency_ms`/`render_prometheus`/`reset` (Task 2) used in 3, 5, 6; `SLO`/`default_slos`/`evaluate`/`build_health_report` (Task 3) used in 6; `correlation_id_var`/`configure_logging`/`add_correlation_id`/`get_logger` (Task 4) used in 5, 6; `ObservabilityMiddleware(app, metrics=…)` (Task 5) mounted in 6. The SLO keys `request_latency_p99_ms`/`error_rate_pct` match between `slo.py`, the tests, and `/health`. Compose service names (`app`, `traefik`) and the `{{ project_slug }}.localhost` host match across `base.yml`, `dev.yml`, `SERVICES.md`, and the render tests. Any test file importing the generated package is a `.jinja` template (so `{{ package_name }}` interpolates); pure-logic modules (`metrics.py`, `slo.py`, `logging_config.py`, `middleware/observability.py`) are static `.py` and use relative imports or `TYPE_CHECKING`-guarded package imports.

---

*End of plan.*
