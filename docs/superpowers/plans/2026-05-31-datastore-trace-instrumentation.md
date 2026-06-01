# Data-store Trace Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-instrument the generated app's data stores (SQLAlchemy always; pymongo/redis per battery) with OpenTelemetry so every DB/cache query produces a span, in both the app and worker processes.

**Architecture:** A new jinja-gated `observability/datastores.py` exposes `configure_datastore_instrumentation(settings)` — no-op when OTel is off, else instruments SQLAlchemy (against the module-level engine) plus pymongo/redis when those batteries are present. Both `configure_tracing` (app) and `configure_worker_tracing` (worker) call it after building the tracer provider.

**Tech Stack:** Python 3.12, OpenTelemetry SDK + `opentelemetry-instrumentation-{sqlalchemy,pymongo,redis}`, SQLAlchemy / pymongo / redis, Copier (Jinja) template, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-05-31-datastore-trace-instrumentation-design.md`

---

## Conventions (read first)

- `FW` = framework repo root (`/home/chris/Claude Code/Projects/framework/swiftwater-framework`). Run `uv` commands from there. You are on branch `obs-datastore-tracing-2026-05-31` — do NOT switch branches.
- **Template payload is not framework source.** Files under `src/framework_cli/template/` are Jinja-rendered into generated projects; validate by rendering and exercising the generated project, not by importing them in the framework venv.
- **Rendered-project test loop** (the worker-tracing/datastores tests run in a generated project that has SQLAlchemy/pymongo/redis + the OTel instrumentors installed — the framework venv does not). One-time setup (render ALL batteries so `datastores.py` contains all three store blocks):
  ```bash
  rm -rf /tmp/ds-work && uv run framework template-render --out /tmp/ds-work >/dev/null
  (cd /tmp/ds-work && uv sync --quiet)
  ```
  (`template-render` with no `--batteries` defaults to ALL batteries.) After editing template source, mirror by RENDERING and copying the rendered file (never hand-substitute Jinja):
  ```bash
  rm -rf /tmp/ds-render && uv run framework template-render --out /tmp/ds-render >/dev/null
  cp /tmp/ds-render/src/demo/observability/datastores.py /tmp/ds-work/src/demo/observability/datastores.py
  cp /tmp/ds-render/src/demo/observability/tracing.py     /tmp/ds-work/src/demo/observability/tracing.py
  cp /tmp/ds-render/tests/unit/test_datastore_instrumentation.py /tmp/ds-work/tests/unit/test_datastore_instrumentation.py
  ```
  Run a test: `(cd /tmp/ds-work && uv run pytest tests/unit/test_datastore_instrumentation.py -q)`.
- **`Settings`** (pydantic-settings) supports `Settings(otel_enabled=...)`; `otel_enabled`/`service_name`/`otel_exporter_otlp_endpoint` all have defaults.
- **COMMIT-GATE HOOK:** a PreToolUse hook blocks `git commit` unless `CLAUDE.md` is staged. For each commit: (1) add a BRIEF note to the **Current State** pointer at the top of `CLAUDE.md` (one sentence; the pointer was just compressed — keep it short) and bump **Last updated**; (2) `git add CLAUDE.md <files>` as a SEPARATE command; (3) `git commit` as its own command (don't chain `add && commit`; keep "commit" out of Bash command *descriptions*). End commit bodies with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Do NOT run the Docker acceptance tier** (it can wedge `/tmp`). The hermetic tests + render checks here are sufficient.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/framework_cli/template/pyproject.toml.jinja` | declare `…-sqlalchemy` (base) + `…-pymongo`/`…-redis` (battery-gated) | 1 |
| `src/framework_cli/template/src/{{package_name}}/observability/datastores.py.jinja` | new — `configure_datastore_instrumentation` | 1 |
| `src/framework_cli/template/tests/unit/{{ 'test_datastore_instrumentation.py' if 'workers' in batteries else '' }}.jinja` | hermetic gating test | 1 |
| `src/framework_cli/template/src/{{package_name}}/observability/tracing.py` | both entrypoints call the datastore instrumentation | 2 |

> Note on the test filename gate: the test imports `datastores` (always present) but its enabled-path assertions reference redis (present when `redis` OR `workers`). Gating the test file on `'workers' in batteries` guarantees redis is installed wherever the test renders, and the ALL-batteries working project includes it. The test body is further jinja-gated per store (below).

---

## Task 1: Dependencies + the datastores instrumentation module

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Create: `src/framework_cli/template/src/{{package_name}}/observability/datastores.py.jinja`
- Create: `src/framework_cli/template/tests/unit/{{ 'test_datastore_instrumentation.py' if 'workers' in batteries else '' }}.jinja`

- [ ] **Step 1: Add the instrumentor dependencies**

In `src/framework_cli/template/pyproject.toml.jinja`:

(a) In the base `dependencies` array, immediately after the line `    "opentelemetry-instrumentation-fastapi>=0.48b0",`, add:
```
    "opentelemetry-instrumentation-sqlalchemy>=0.48b0",
```

(b) In the mongodb-gated block, change:
```jinja
{% endif %}{% if "mongodb" in batteries %}    "pymongo>=4.9",
{% endif %}
```
to:
```jinja
{% endif %}{% if "mongodb" in batteries %}    "pymongo>=4.9",
    "opentelemetry-instrumentation-pymongo>=0.48b0",
{% endif %}
```

(c) Immediately after the redis-gated block (`{% endif %}{% if "redis" in batteries %}    "redis>=5",` + its `{% endif %}`), add a new gated line for the redis instrumentor (gated on redis OR workers, since the workers battery uses redis as its broker):
```jinja
{% endif %}{% if "redis" in batteries or "workers" in batteries %}    "opentelemetry-instrumentation-redis>=0.48b0",
{% endif %}
```
Place it so it sits between the `redis>=5` block's `{% endif %}` and the `{% if "consumers" in batteries %}` block.

- [ ] **Step 2: Render + sync the working project; confirm the instrumentors import**

```bash
rm -rf /tmp/ds-work && uv run framework template-render --out /tmp/ds-work >/dev/null
(cd /tmp/ds-work && uv sync --quiet)
(cd /tmp/ds-work && uv run python -c "import opentelemetry.instrumentation.sqlalchemy, opentelemetry.instrumentation.pymongo, opentelemetry.instrumentation.redis; print('instrumentors importable')")
```
Expected: `instrumentors importable`.

- [ ] **Step 3: Write the failing hermetic gating test**

Create `src/framework_cli/template/tests/unit/{{ 'test_datastore_instrumentation.py' if 'workers' in batteries else '' }}.jinja`:

```python
"""Data-store auto-instrumentation gating (hermetic — no real engines/clients).

Each store instrumentor's .instrument is monkeypatched to record, so we verify the
gating/wiring without opening a DB connection or patching libraries globally.
"""

from {{ package_name }}.config.settings import Settings
from {{ package_name }}.observability import datastores


def test_noop_when_otel_disabled():
    # Disabled: returns without importing the SDK / instrumenting (must not raise).
    datastores.configure_datastore_instrumentation(Settings(otel_enabled=False))


def test_instruments_present_stores_when_enabled(monkeypatch):
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    calls: list[str] = []
    monkeypatch.setattr(
        SQLAlchemyInstrumentor, "instrument", lambda self, **k: calls.append("sqlalchemy")
    )
{%- if "mongodb" in batteries %}
    from opentelemetry.instrumentation.pymongo import PymongoInstrumentor

    monkeypatch.setattr(
        PymongoInstrumentor, "instrument", lambda self, **k: calls.append("pymongo")
    )
{%- endif %}
{%- if "redis" in batteries or "workers" in batteries %}
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    monkeypatch.setattr(
        RedisInstrumentor, "instrument", lambda self, **k: calls.append("redis")
    )
{%- endif %}

    datastores.configure_datastore_instrumentation(Settings(otel_enabled=True))

    assert "sqlalchemy" in calls
{%- if "mongodb" in batteries %}
    assert "pymongo" in calls
{%- endif %}
{%- if "redis" in batteries or "workers" in batteries %}
    assert "redis" in calls
{%- endif %}
```

- [ ] **Step 4: Mirror + run to verify it fails**

```bash
rm -rf /tmp/ds-render && uv run framework template-render --out /tmp/ds-render >/dev/null
cp /tmp/ds-render/tests/unit/test_datastore_instrumentation.py /tmp/ds-work/tests/unit/test_datastore_instrumentation.py
(cd /tmp/ds-work && uv run pytest tests/unit/test_datastore_instrumentation.py -q)
```
Expected: FAIL — `ModuleNotFoundError`/`ImportError` on `{{ package_name }}.observability.datastores` (the module doesn't exist yet), i.e. a collection error.

- [ ] **Step 5: Create the datastores module**

Create `src/framework_cli/template/src/{{package_name}}/observability/datastores.py.jinja`:

```python
"""Data-store OpenTelemetry auto-instrumentation (SQLAlchemy + battery stores).

Instruments the store client libraries so DB/cache queries produce spans that continue
the trace from the triggering request or task. Called once per process from the app
(configure_tracing) and the worker (configure_worker_tracing). OTel imports are lazy so
a disabled process never imports the SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config.settings import Settings


def configure_datastore_instrumentation(settings: "Settings") -> None:
    """Auto-instrument the data stores for tracing (no-op when OTel is disabled)."""
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

- [ ] **Step 6: Mirror + run to verify it passes**

```bash
rm -rf /tmp/ds-render && uv run framework template-render --out /tmp/ds-render >/dev/null
cp /tmp/ds-render/src/demo/observability/datastores.py /tmp/ds-work/src/demo/observability/datastores.py
cp /tmp/ds-render/tests/unit/test_datastore_instrumentation.py /tmp/ds-work/tests/unit/test_datastore_instrumentation.py
(cd /tmp/ds-work && uv run pytest tests/unit/test_datastore_instrumentation.py -q)
```
Expected: PASS (2 passed).

- [ ] **Step 7: Confirm rendered format is clean**

```bash
(cd /tmp/ds-render && uv run ruff format --check src/demo/observability/datastores.py tests/unit/test_datastore_instrumentation.py)
```
Expected: `... files already formatted`. If a file would reformat, fix the wrapping in the TEMPLATE source and re-render until clean.

- [ ] **Step 8: Commit**

Update the CLAUDE.md Current State pointer (one brief sentence + bump Last updated), then:
```bash
git add CLAUDE.md \
  "src/framework_cli/template/pyproject.toml.jinja" \
  "src/framework_cli/template/src/{{package_name}}/observability/datastores.py.jinja" \
  "src/framework_cli/template/tests/unit/{{ 'test_datastore_instrumentation.py' if 'workers' in batteries else '' }}.jinja"
git commit -m "feat(template): data-store OTel auto-instrumentation module + deps"
```

---

## Task 2: Wire both tracing entrypoints to instrument the data stores

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/observability/tracing.py`
- Modify: `src/framework_cli/template/tests/unit/{{ 'test_worker_tracing.py' if 'workers' in batteries else '' }}.jinja` (add 2 wiring tests)

- [ ] **Step 1: Write the failing wiring tests**

Append to `src/framework_cli/template/tests/unit/{{ 'test_worker_tracing.py' if 'workers' in batteries else '' }}.jinja`:

```python
def test_configure_tracing_invokes_datastore_instrumentation(monkeypatch):
    # The app path must instrument the data stores after building the provider.
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    calls: list[str] = []
    monkeypatch.setattr(tracing, "_build_tracer_provider", lambda s: calls.append("provider"))
    monkeypatch.setattr(FastAPIInstrumentor, "instrument_app", lambda app: calls.append("fastapi"))
    monkeypatch.setattr(
        tracing, "configure_datastore_instrumentation", lambda s: calls.append("datastores")
    )
    tracing.configure_tracing(object(), Settings(otel_enabled=True))
    assert "datastores" in calls


def test_configure_worker_tracing_invokes_datastore_instrumentation(monkeypatch):
    # The worker path must instrument the data stores too (workers hit the DB + redis).
    import opentelemetry.instrumentation.celery as cel

    calls: list[str] = []
    monkeypatch.setattr(tracing, "_build_tracer_provider", lambda s: calls.append("provider"))
    monkeypatch.setattr(cel.CeleryInstrumentor, "instrument", lambda self, **k: calls.append("celery"))
    monkeypatch.setattr(
        tracing, "configure_datastore_instrumentation", lambda s: calls.append("datastores")
    )
    tracing.configure_worker_tracing(Settings(otel_enabled=True))
    assert "datastores" in calls
```

(These monkeypatch `tracing.configure_datastore_instrumentation`, which requires it to be a module-level name in `tracing.py` — added in Step 3.)

- [ ] **Step 2: Mirror + run to verify they fail**

```bash
rm -rf /tmp/ds-render && uv run framework template-render --out /tmp/ds-render >/dev/null
cp /tmp/ds-render/tests/unit/test_worker_tracing.py /tmp/ds-work/tests/unit/test_worker_tracing.py
(cd /tmp/ds-work && uv run pytest tests/unit/test_worker_tracing.py -q)
```
Expected: the two new tests FAIL — `AttributeError: <module 'demo.observability.tracing'> has no attribute 'configure_datastore_instrumentation'` (monkeypatch with `raising=True` errors because the name isn't imported yet). The four prior worker-tracing tests still PASS.

- [ ] **Step 3: Wire tracing.py**

In `src/framework_cli/template/src/{{package_name}}/observability/tracing.py`:

(a) Add a top-level import after the `from __future__ import annotations` line (before or after the `from typing import TYPE_CHECKING` line):
```python
from .datastores import configure_datastore_instrumentation
```
(Safe to import at module top: `datastores.py` has no top-level OTel imports — only inside its function — so this does not import the SDK on the disabled path.)

(b) In `configure_tracing`, append the datastore call as the LAST line of the function body:
```python
def configure_tracing(app: "FastAPI", settings: "Settings") -> None:
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _build_tracer_provider(settings)
    FastAPIInstrumentor.instrument_app(app)
    configure_datastore_instrumentation(settings)
```

(c) In `configure_worker_tracing`, append the datastore call as the LAST line of the function body:
```python
def configure_worker_tracing(settings: "Settings") -> None:
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    _build_tracer_provider(settings)
    CeleryInstrumentor().instrument()
    configure_datastore_instrumentation(settings)
```

- [ ] **Step 4: Mirror + run to verify they pass (+ no regression)**

```bash
rm -rf /tmp/ds-render && uv run framework template-render --out /tmp/ds-render >/dev/null
cp /tmp/ds-render/src/demo/observability/tracing.py /tmp/ds-work/src/demo/observability/tracing.py
(cd /tmp/ds-work && uv run pytest tests/unit/test_worker_tracing.py tests/unit/test_datastore_instrumentation.py tests/unit/test_tracing.py -q)
```
Expected: PASS (6 in test_worker_tracing.py + 2 in test_datastore_instrumentation.py + the existing test_tracing.py cases) — no regression in the FastAPI/worker tracing paths.

- [ ] **Step 5: Confirm rendered format is clean**

```bash
(cd /tmp/ds-render && uv run ruff format --check src/demo/observability/tracing.py tests/unit/test_worker_tracing.py)
```
Expected: `... files already formatted` (fix wrapping in template source + re-render if not).

- [ ] **Step 6: Commit**

Update the CLAUDE.md pointer (brief), then:
```bash
git add CLAUDE.md \
  "src/framework_cli/template/src/{{package_name}}/observability/tracing.py" \
  "src/framework_cli/template/tests/unit/{{ 'test_worker_tracing.py' if 'workers' in batteries else '' }}.jinja"
git commit -m "feat(template): instrument data stores from both tracing entrypoints"
```

---

## Task 3: Whole-slice verification

**Files:** none (verification only).

- [ ] **Step 1: Gating sanity — a no-mongodb/no-redis render omits those blocks**

```bash
rm -rf /tmp/ds-min && uv run framework template-render --out /tmp/ds-min --batteries pgvector >/dev/null
grep -c "SQLAlchemyInstrumentor" /tmp/ds-min/src/demo/observability/datastores.py   # expect 1
grep -c "PymongoInstrumentor"    /tmp/ds-min/src/demo/observability/datastores.py   # expect 0
grep -c "RedisInstrumentor"      /tmp/ds-min/src/demo/observability/datastores.py   # expect 0
```
Expected: `1`, `0`, `0` — SQLAlchemy always; pymongo/redis blocks gated out when their batteries are absent.

- [ ] **Step 2: Eval-fixture safety scan (expect broken: 0)**

```bash
python3 - <<'PY'
import subprocess, tempfile, yaml, shutil
from pathlib import Path
cache={}
def render(b):
    k=",".join(sorted(b)) or "_none_"
    if k in cache: return cache[k]
    d=tempfile.mkdtemp(prefix="fx-"); subprocess.run(["uv","run","framework","template-render","--out",d,"--batteries",",".join(b)],capture_output=True,text=True); cache[k]=d; return d
bad=0
for p in sorted(Path("tests/eval/fixtures").glob("*/*/*/change.patch")):
    b=(yaml.safe_load((p.parent/"fixture.yaml").read_text()) or {}).get("batteries",[])
    if subprocess.run(["git","apply","--check","-p1",str(p.resolve())],cwd=render(b),capture_output=True,text=True).returncode!=0:
        bad+=1; print("BROKEN",p.parent)
print("broken:",bad)
for d in cache.values(): shutil.rmtree(d,ignore_errors=True)
PY
```
Expected: `broken: 0`.

- [ ] **Step 3: Full framework gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run mypy src
```
Expected: all pass, ruff clean, mypy clean.

- [ ] **Step 4: Clean up working dirs**

```bash
rm -rf /tmp/ds-work /tmp/ds-render /tmp/ds-min
rm -rf /tmp/pytest-of-chris/* 2>/dev/null
```

---

## Notes for the implementer

- **Spans, not metrics.** This slice deliberately adds no per-query Prometheus metrics (high cardinality). Query latency lives in traces (Tempo). Do not add `record_query`-style counters.
- **No client `health()`.** The `/health` route already pings mongo + redis; do not add client-level health functions (verified false-positive in the audit triage).
- **Lazy imports** stay inside `configure_datastore_instrumentation` and the tracing entrypoints, so the disabled path (tests/lite/local) never imports the OTel SDK. The one exception is the top-level `from .datastores import configure_datastore_instrumentation` in `tracing.py` — safe because `datastores.py` has no module-level OTel imports.
- SQLAlchemy auto-instrumentation (bound to the shared `db.engine.engine`) covers the `pgvector`/`timescaledb`/`age` repositories too — they all use the same engine/session.
