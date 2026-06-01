# Worker Tracing + OTEL Env-Parity Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Celery workers emit OpenTelemetry traces (they currently emit only metrics), wired consistently across dev + prod, and add a framework-side guard test that every app-image compose service carries the OTEL env.

**Architecture:** Refactor the template's `observability/tracing.py` into a shared `_build_tracer_provider` consumed by both the existing FastAPI path and a new `configure_worker_tracing` (CeleryInstrumentor). A fork-safe `worker_process_init` handler in the Celery bootstrap initializes tracing per worker child. `worker`/`beat` get `APP_OTEL_*` env in `dev.yml` + `services.yml`. A framework test renders a workers project and asserts the OTEL env parity by parsing compose YAML (no Docker).

**Tech Stack:** Python 3.12, Celery, OpenTelemetry SDK + `opentelemetry-instrumentation-celery`, Copier (Jinja) template, pytest, PyYAML, `uv`.

**Spec:** `docs/superpowers/specs/2026-05-31-worker-tracing-env-parity-design.md`

---

## Conventions (read first)

- `FW` = framework repo root (`/home/chris/Claude Code/Projects/framework/swiftwater-framework`). Run all `uv` commands from there unless stated.
- **Template payload is not framework source.** Files under `src/framework_cli/template/` are Jinja-rendered into generated projects; the framework's own mypy excludes them. They are validated by *rendering* and exercising the generated project.
- Brace-named paths like `src/{{package_name}}/...` and `{% if "workers" in batteries %}tasks{% endif %}/` are intentional Copier path templating — quote them in shell.
- **Rendered-project test loop** (for Tasks 2 & 3, whose tests run in a generated project that has Celery/OTel installed — the framework venv does not):

  ```bash
  # one-time working project (workers + its redis broker), with deps installed
  rm -rf /tmp/wt-work && uv run framework template-render --out /tmp/wt-work --batteries workers,redis >/dev/null
  (cd /tmp/wt-work && uv sync --quiet)
  ```

  After editing a template **source** file, mirror it into the working project, then run the target test there:
  - plain `.py` (e.g. `tracing.py`): `cp "<template path>" /tmp/wt-work/src/demo/<rel>`
  - `.jinja` files (e.g. `app.py.jinja`, test `.jinja`): re-render and copy the rendered file:
    ```bash
    rm -rf /tmp/wt-render && uv run framework template-render --out /tmp/wt-render --batteries workers,redis >/dev/null
    cp /tmp/wt-render/src/demo/tasks/app.py /tmp/wt-work/src/demo/tasks/app.py
    cp /tmp/wt-render/tests/unit/test_worker_tracing.py /tmp/wt-work/tests/unit/test_worker_tracing.py
    ```
  - run a test: `(cd /tmp/wt-work && uv run pytest tests/unit/test_worker_tracing.py -q)`
- **Settings fields used:** `otel_enabled: bool`, `service_name: str`, `otel_exporter_otlp_endpoint: str` (all already on `Settings`, consumed by the current `configure_tracing`).

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `tests/test_env_parity_otel.py` (framework) | Guard: every app-image service carries `APP_OTEL_*` | 1 |
| `src/framework_cli/template/infra/compose/dev.yml.jinja` | `APP_OTEL_*` on dev `worker`+`beat` | 1 |
| `src/framework_cli/template/infra/compose/services.yml.jinja` | `APP_OTEL_*` on prod `worker`+`beat` | 1 |
| `src/framework_cli/template/src/{{package_name}}/observability/tracing.py` | shared `_build_tracer_provider`; new `configure_worker_tracing` | 2 |
| `src/framework_cli/template/tests/unit/{{ 'test_worker_tracing.py' if 'workers' in batteries else '' }}.jinja` | rendered-project unit tests for worker tracing | 2, 3 |
| `src/framework_cli/template/pyproject.toml.jinja` | `opentelemetry-instrumentation-celery` (workers-gated) | 3 |
| `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/app.py.jinja` | `worker_process_init` bootstrap | 3 |

---

## Task 1: Compose OTEL env on worker/beat + framework env-parity guard

**Files:**
- Create: `tests/test_env_parity_otel.py`
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja` (worker + beat `environment:` blocks)
- Modify: `src/framework_cli/template/infra/compose/services.yml.jinja` (worker + beat `environment:` blocks)

- [ ] **Step 1: Write the failing guard test**

Create `tests/test_env_parity_otel.py`:

```python
"""Env-parity guard: every app-image compose service must carry the OTEL env.

The app gets APP_OTEL_* via the observability.yml overlay; worker/beat are defined
in dev.yml + services.yml and must carry the same vars so they export traces in
every environment. Per-file YAML parse — no Docker.
"""

from pathlib import Path

import yaml

from framework_cli.copier_runner import render_project

_OTEL_VARS = {"APP_OTEL_ENABLED", "APP_OTEL_EXPORTER_OTLP_ENDPOINT"}


def _services(path: Path) -> dict:
    return (yaml.safe_load(path.read_text()) or {}).get("services", {})


def test_app_image_services_carry_otel_env(tmp_path):
    root = tmp_path / "proj"
    render_project(
        root,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
            "batteries": ["workers", "redis"],
        },
    )
    # app: OTEL via the observability overlay
    obs = _services(root / "infra/compose/observability.yml")
    assert _OTEL_VARS <= set(obs["app"]["environment"]), "app missing OTEL env"

    # worker + beat: OTEL in BOTH dev.yml and the prod/staging services.yml overlay
    dev = _services(root / "infra/compose/dev.yml")
    svc = _services(root / "infra/compose/services.yml")
    for name in ("worker", "beat"):
        assert _OTEL_VARS <= set(dev[name]["environment"]), f"dev.yml {name} missing OTEL env"
        assert _OTEL_VARS <= set(svc[name]["environment"]), f"services.yml {name} missing OTEL env"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_env_parity_otel.py -q`
Expected: FAIL — `dev.yml worker missing OTEL env` (worker/beat have no `APP_OTEL_*` yet).

- [ ] **Step 3: Add the OTEL env to dev.yml worker + beat**

In `src/framework_cli/template/infra/compose/dev.yml.jinja`, the dev `worker` `environment:` block ends with `APP_DATABASE_URL: "postgresql+psycopg://app:app@postgres:5432/app"`. Append two lines so it reads:

```yaml
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
      APP_DATABASE_URL: "postgresql+psycopg://app:app@postgres:5432/app"
      APP_OTEL_ENABLED: "true"
      APP_OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
```

The dev `beat` `environment:` block ends with `APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"`. Append the same two lines so it reads:

```yaml
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
      APP_OTEL_ENABLED: "true"
      APP_OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
```

- [ ] **Step 4: Add the OTEL env to services.yml worker + beat**

In `src/framework_cli/template/infra/compose/services.yml.jinja`, the prod `worker` `environment:` block ends with `APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"`. Append the same two lines:

```yaml
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
      APP_OTEL_ENABLED: "true"
      APP_OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
```

The prod `beat` `environment:` block likewise ends with `APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"`. Append the same two lines.

(All four blocks point at the same in-network collector the app uses; the `app` service is wired in `observability.yml` and is unchanged.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_env_parity_otel.py -q`
Expected: PASS.

- [ ] **Step 6: Confirm the rendered compose still parses and merges**

Run:
```bash
rm -rf /tmp/wt-render && uv run framework template-render --out /tmp/wt-render --batteries workers,redis >/dev/null
python3 -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ['/tmp/wt-render/infra/compose/dev.yml','/tmp/wt-render/infra/compose/services.yml']]; print('yaml ok')"
```
Expected: `yaml ok` (valid YAML, no Jinja artifacts).

- [ ] **Step 7: Commit**

```bash
git add tests/test_env_parity_otel.py \
  "src/framework_cli/template/infra/compose/dev.yml.jinja" \
  "src/framework_cli/template/infra/compose/services.yml.jinja" \
  CLAUDE.md
git commit -m "feat(template): wire APP_OTEL_* on worker/beat + env-parity guard test"
```
(Update the CLAUDE.md Current State pointer first — the commit hook requires it staged.)

---

## Task 2: Refactor tracing.py — shared provider + configure_worker_tracing

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/observability/tracing.py`
- Create: `src/framework_cli/template/tests/unit/{{ 'test_worker_tracing.py' if 'workers' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing rendered-project test**

Create `src/framework_cli/template/tests/unit/{{ 'test_worker_tracing.py' if 'workers' in batteries else '' }}.jinja`:

```python
"""Worker-tracing setup (hermetic). Validates the shared provider builder and the
Celery worker tracing entrypoint without standing up an exporter or a worker."""

from {{ package_name }}.config.settings import Settings
from {{ package_name }}.observability import tracing


def test_configure_worker_tracing_is_noop_when_disabled():
    # OTel off: returns without importing the SDK / instrumenting (must not raise).
    tracing.configure_worker_tracing(Settings(otel_enabled=False))


def test_build_tracer_provider_carries_service_name():
    provider = tracing._build_tracer_provider(
        Settings(otel_enabled=True, service_name="demo-svc")
    )
    assert provider.resource.attributes["service.name"] == "demo-svc"
```

- [ ] **Step 2: Mirror + run to verify it fails**

```bash
rm -rf /tmp/wt-render && uv run framework template-render --out /tmp/wt-render --batteries workers,redis >/dev/null
cp /tmp/wt-render/tests/unit/test_worker_tracing.py /tmp/wt-work/tests/unit/test_worker_tracing.py
(cd /tmp/wt-work && uv run pytest tests/unit/test_worker_tracing.py -q)
```
Expected: FAIL — `AttributeError: module ... has no attribute 'configure_worker_tracing'` (and `_build_tracer_provider`).

- [ ] **Step 3: Refactor tracing.py**

Replace the body of `src/framework_cli/template/src/{{package_name}}/observability/tracing.py` (keep the module docstring; update the `TYPE_CHECKING` block to add `TracerProvider`) so it reads:

```python
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
```

- [ ] **Step 4: Mirror + run to verify it passes**

```bash
cp "src/framework_cli/template/src/{{package_name}}/observability/tracing.py" /tmp/wt-work/src/demo/observability/tracing.py
(cd /tmp/wt-work && uv run pytest tests/unit/test_worker_tracing.py -q)
```
Expected: PASS (2 passed).

- [ ] **Step 5: Confirm the FastAPI path is unchanged**

Run the existing app tracing test in the working project:
```bash
(cd /tmp/wt-work && uv run pytest tests/unit/test_tracing.py -q)
```
Expected: PASS (no regression in `configure_tracing`).

- [ ] **Step 6: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/observability/tracing.py" \
  "src/framework_cli/template/tests/unit/{{ 'test_worker_tracing.py' if 'workers' in batteries else '' }}.jinja" \
  CLAUDE.md
git commit -m "feat(template): share tracer-provider setup + add configure_worker_tracing"
```

---

## Task 3: Celery dep + worker_process_init bootstrap

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja` (workers-gated deps)
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/app.py.jinja`
- Modify: `src/framework_cli/template/tests/unit/{{ 'test_worker_tracing.py' if 'workers' in batteries else '' }}.jinja` (add 2 tests)

- [ ] **Step 1: Add the Celery OTel instrumentation dependency**

In `src/framework_cli/template/pyproject.toml.jinja`, the workers-gated dependency line is:

```jinja
{% endif %}{% if "workers" in batteries %}    "celery[redis]>=5.4",
{% endif %}
```

Change it to add the instrumentation package (same version floor as the base `opentelemetry-instrumentation-fastapi>=0.48b0`):

```jinja
{% endif %}{% if "workers" in batteries %}    "celery[redis]>=5.4",
    "opentelemetry-instrumentation-celery>=0.48b0",
{% endif %}
```

- [ ] **Step 2: Re-sync the working project so the new dep is installed**

```bash
rm -rf /tmp/wt-render && uv run framework template-render --out /tmp/wt-render --batteries workers,redis >/dev/null
cp /tmp/wt-render/pyproject.toml /tmp/wt-work/pyproject.toml
(cd /tmp/wt-work && uv sync --quiet)
python3 -c "import importlib.util,sys; sys.path.insert(0,'/tmp/wt-work/.venv/lib/python3.12/site-packages'); import opentelemetry.instrumentation.celery; print('celery instrumentation importable')"
```
Expected: `celery instrumentation importable`.

- [ ] **Step 3: Write the failing bootstrap tests**

Append to the test `.jinja` (`tests/unit/{{ 'test_worker_tracing.py' ... }}.jinja`):

```python
def test_configure_worker_tracing_instruments_when_enabled(monkeypatch):
    # Avoid global side effects: record the two collaborators instead of running them.
    import opentelemetry.instrumentation.celery as cel

    calls = []
    monkeypatch.setattr(tracing, "_build_tracer_provider", lambda s: calls.append("provider"))
    monkeypatch.setattr(cel.CeleryInstrumentor, "instrument", lambda self, **k: calls.append("instrument"))
    tracing.configure_worker_tracing(Settings(otel_enabled=True))
    assert calls == ["provider", "instrument"]


def test_worker_process_init_fires_tracing_setup(monkeypatch):
    # Firing the signal must reach our handler, which delegates to
    # configure_worker_tracing(get_settings()). Sending the signal exercises both
    # the registration and the delegation without touching Celery signal internals.
    from celery.signals import worker_process_init

    from {{ package_name }}.tasks import app as tasks_app

    seen = {}
    monkeypatch.setattr(tasks_app, "configure_worker_tracing", lambda s: seen.setdefault("s", s))
    worker_process_init.send(sender=None)
    assert "s" in seen
```

- [ ] **Step 4: Mirror + run to verify they fail**

```bash
rm -rf /tmp/wt-render && uv run framework template-render --out /tmp/wt-render --batteries workers,redis >/dev/null
cp /tmp/wt-render/tests/unit/test_worker_tracing.py /tmp/wt-work/tests/unit/test_worker_tracing.py
(cd /tmp/wt-work && uv run pytest tests/unit/test_worker_tracing.py -q)
```
Expected: `test_configure_worker_tracing_instruments_when_enabled` PASS (its implementation landed in Task 2; this is the first run with the dep installed), and `test_worker_process_init_fires_tracing_setup` FAIL — `AttributeError: module ... has no attribute 'configure_worker_tracing'` on `tasks.app` (the bootstrap import + handler don't exist yet).

- [ ] **Step 5: Add the worker_process_init bootstrap to app.py**

In `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/app.py.jinja`:

Change the imports near the top from:

```python
from celery import Celery

from ..config.settings import get_settings
```

to:

```python
from celery import Celery
from celery.signals import worker_process_init

from ..config.settings import get_settings
from ..observability.tracing import configure_worker_tracing
```

Then, immediately **after** the `app.conf.update(...)` call and **before** the `from .schedule import register_schedule` line, add:

```python
@worker_process_init.connect
def _init_worker_tracing(**_kwargs: object) -> None:
    """Initialize OTel tracing in each worker child process (fork-safe).

    Runs after the prefork pool forks, so the BatchSpanProcessor export thread is
    created in the child that uses it (creating it pre-fork would silently drop spans).
    No-op when OTel is disabled.
    """
    configure_worker_tracing(get_settings())
```

- [ ] **Step 6: Mirror + run to verify they pass**

```bash
rm -rf /tmp/wt-render && uv run framework template-render --out /tmp/wt-render --batteries workers,redis >/dev/null
cp /tmp/wt-render/src/demo/tasks/app.py /tmp/wt-work/src/demo/tasks/app.py
(cd /tmp/wt-work && uv run pytest tests/unit/test_worker_tracing.py -q)
```
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add "src/framework_cli/template/pyproject.toml.jinja" \
  "src/framework_cli/template/src/{{package_name}}/{% if \"workers\" in batteries %}tasks{% endif %}/app.py.jinja" \
  "src/framework_cli/template/tests/unit/{{ 'test_worker_tracing.py' if 'workers' in batteries else '' }}.jinja" \
  CLAUDE.md
git commit -m "feat(template): trace Celery workers via fork-safe worker_process_init bootstrap"
```

---

## Task 4: Whole-slice verification

**Files:** none (verification only).

- [ ] **Step 1: Rendered project — format + the full worker test file**

```bash
rm -rf /tmp/wt-render && uv run framework template-render --out /tmp/wt-render --batteries workers,redis >/dev/null
(cd /tmp/wt-render && uv run ruff format --check src/demo/observability/tracing.py src/demo/tasks/app.py tests/unit/test_worker_tracing.py)
```
Expected: `... files already formatted`. If it reports a file would be reformatted, hand-wrap the offending lines in the **template source** (the long-line regression class) and re-render until clean.

- [ ] **Step 2: Eval-fixture safety scan (no fixture should have broken)**

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
    d=render(b)
    if subprocess.run(["git","apply","--check","-p1",str(p.resolve())],cwd=d,capture_output=True,text=True).returncode!=0:
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
Expected: all pass (the new framework guard test included), ruff clean, mypy clean.

- [ ] **Step 4: (Optional) Docker merge spot-check**

If Docker is available and `/tmp` is healthy, confirm the merged prod config wires worker OTEL:
```bash
(cd /tmp/wt-render && docker compose -f infra/compose/prod.yml -f infra/compose/services.yml -f infra/compose/observability.yml config 2>/dev/null | grep -A2 "APP_OTEL_ENABLED" | head) || echo "skip (docker/tmp)"
```
Expected: the worker/beat services show `APP_OTEL_ENABLED`. Skip per the standing `/tmp`-wedge caveat if unsure.

- [ ] **Step 5: Clean up working dirs**

```bash
rm -rf /tmp/wt-work /tmp/wt-render
rm -rf /tmp/pytest-of-chris/* 2>/dev/null
```

---

## Notes for the implementer

- **Fork-safety is the whole point** of `worker_process_init` — do not "simplify" it to import-time/module-level initialization (the exporter thread would be created pre-fork and silently stop in the children).
- `configure_tracing`'s observable behavior must not change — Step 5 of Task 2 guards that.
- Keep all OTel imports **inside** functions (lazy) so disabled processes (tests, `dev:lite`, local uvicorn) never import the SDK.
- The compose env additions are identical 2-line blocks in 4 places (dev worker, dev beat, prod worker, prod beat) — the only `app`-image services besides `app` itself.
