# Obs Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound the generated app's in-process latency samples to a fixed window, and log the GraphQL introspection/IDE toggle at router construction.

**Architecture:** Two small, independent template-payload fixes. (1) `MetricsRegistry._latencies_ms` becomes a `deque(maxlen=N)` so memory + per-scrape sort cost stay constant (windowed p99). (2) `routes/graphql.py`'s router wiring moves into a `_configure_graphql_router()` factory that logs the introspection/IDE decision. Both get hermetic rendered-project tests.

**Tech Stack:** Python 3.12 (`collections.deque`), structlog, Strawberry GraphQL, Copier (Jinja) template, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-01-obs-hygiene-design.md`

---

## Conventions (read first)

- `FW` = framework repo root (`/home/chris/Claude Code/Projects/framework/swiftwater-framework`). You are on branch `obs-hygiene-2026-06-01` — do NOT switch branches.
- **Template payload:** the edited files render into generated projects. Their tests run in a GENERATED project (not the framework venv). Rendered-project loop (one-time):
  ```bash
  rm -rf /tmp/oh-work && uv run framework template-render --out /tmp/oh-work >/dev/null
  (cd /tmp/oh-work && uv sync --quiet)
  ```
  Mirror after editing template source, then run the targeted test:
  - plain `.py` (`metrics.py`): `cp` the template source directly to the rendered path.
  - `.jinja` files (`graphql.py.jinja`, the test `.jinja`s): re-render to `/tmp/oh-render` and `cp` the rendered file.
  ```bash
  rm -rf /tmp/oh-render && uv run framework template-render --out /tmp/oh-render >/dev/null
  cp /tmp/oh-render/<rel> /tmp/oh-work/<rel>
  (cd /tmp/oh-work && uv run pytest <test> -q)
  ```
- **COMMIT-GATE HOOK:** a PreToolUse hook blocks `git commit` unless `CLAUDE.md` is staged. Per commit: add a BRIEF note to the Current State pointer + bump **Last updated**; `git add CLAUDE.md <files>` (separate command); then `git commit` (its own command; keep "commit" out of Bash descriptions). Trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. In a subagent session the gate may BLOCK (it needs the `Workflow` tool subagents lack) — if so, stage everything and report DONE; the controller commits.
- **Do NOT run the Docker acceptance tier.**

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/framework_cli/template/src/{{package_name}}/observability/metrics.py` | bounded latency deque | 1 |
| `src/framework_cli/template/tests/unit/test_metrics.py.jinja` | latency-window-bounded test | 1 |
| `src/framework_cli/template/src/{{package_name}}/routes/{{ 'graphql.py' if 'graphql' in batteries else '' }}.jinja` | `_configure_graphql_router()` factory + toggle log | 2 |
| `src/framework_cli/template/tests/unit/{{ 'test_graphql_router.py' if 'graphql' in batteries else '' }}.jinja` | toggle-logged test | 2 |

---

## Task 1: Bound the latency window

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/observability/metrics.py`
- Modify: `src/framework_cli/template/tests/unit/test_metrics.py.jinja`

- [ ] **Step 1: Write the failing test**

Append to `src/framework_cli/template/tests/unit/test_metrics.py.jinja`:

```python
def test_latency_window_is_bounded():
    from {{ package_name }}.observability.metrics import _MAX_LATENCY_SAMPLES

    m = MetricsRegistry()
    for i in range(_MAX_LATENCY_SAMPLES + 100):
        m.record_request(float(i), 200)
    # The window keeps only the most recent _MAX_LATENCY_SAMPLES samples.
    assert len(m._latencies_ms) == _MAX_LATENCY_SAMPLES
    # p99 is still computed (over the bounded window) and finite.
    assert m.p99_latency_ms() > 0.0
```

- [ ] **Step 2: Mirror + run to verify it fails**

```bash
rm -rf /tmp/oh-render && uv run framework template-render --out /tmp/oh-render >/dev/null
cp /tmp/oh-render/tests/unit/test_metrics.py /tmp/oh-work/tests/unit/test_metrics.py
(cd /tmp/oh-work && uv run pytest tests/unit/test_metrics.py -q)
```
Expected: FAIL — `ImportError: cannot import name '_MAX_LATENCY_SAMPLES'` (and, once that exists, `len(...) == _MAX_LATENCY_SAMPLES` would fail against an unbounded list).

- [ ] **Step 3: Bound the deque in metrics.py**

In `src/framework_cli/template/src/{{package_name}}/observability/metrics.py`:

(a) Change the imports from:
```python
import math
import threading
```
to:
```python
import math
import threading
from collections import deque
from collections.abc import Iterable
```

(b) Add the module constant immediately after the imports (before `_PROM_TEMPLATE`):
```python
# Bound the in-process latency window so memory + per-scrape sort cost stay constant.
# p99 is therefore a windowed p99 (the last _MAX_LATENCY_SAMPLES requests).
_MAX_LATENCY_SAMPLES = 2048
```

(c) Change `_p99`'s signature type hint from `def _p99(latencies: list[float]) -> float:` to:
```python
def _p99(latencies: Iterable[float]) -> float:
```
(The body is unchanged — `if not latencies` and `sorted(latencies)` both work on a deque.)

(d) In `MetricsRegistry.__init__`, change `self._latencies_ms: list[float] = []` to:
```python
        self._latencies_ms: deque[float] = deque(maxlen=_MAX_LATENCY_SAMPLES)
```

(e) Reword the module docstring (lines 1-5) to:
```python
"""In-process metrics registry. Fed by the observability middleware; read by /metrics and /health.

A deliberately small, dependency-free store. Latencies are kept in a bounded window (the last
_MAX_LATENCY_SAMPLES requests) so memory and per-scrape sort cost stay constant — p99 is therefore
a windowed p99. Prometheus scrapes /metrics for the fleet-wide / historical view.
"""
```

(`record_request` already does `self._latencies_ms.append(...)` and `reset()` already does `self._latencies_ms.clear()` — both work unchanged on a deque.)

- [ ] **Step 4: Mirror + run to verify it passes (+ no regression)**

```bash
cp "src/framework_cli/template/src/{{package_name}}/observability/metrics.py" /tmp/oh-work/src/demo/observability/metrics.py
(cd /tmp/oh-work && uv run pytest tests/unit/test_metrics.py -q)
```
Expected: PASS — all prior metrics tests (incl. `test_p99_latency` with 100 samples, `test_reset_clears_all_state`) still pass, plus the new bounded-window test.

- [ ] **Step 5: Format check**

```bash
rm -rf /tmp/oh-render && uv run framework template-render --out /tmp/oh-render >/dev/null
(cd /tmp/oh-render && uv run ruff format --check src/demo/observability/metrics.py tests/unit/test_metrics.py)
```
Expected: `... already formatted` (fix wrapping in template source + re-render if not).

- [ ] **Step 6: Commit**

Update CLAUDE.md pointer (brief), then:
```bash
git add CLAUDE.md \
  "src/framework_cli/template/src/{{package_name}}/observability/metrics.py" \
  "src/framework_cli/template/tests/unit/test_metrics.py.jinja"
git commit -m "feat(template): bound MetricsRegistry latency window to a fixed deque"
```

---

## Task 2: Log the GraphQL introspection/IDE toggle

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/{{ 'graphql.py' if 'graphql' in batteries else '' }}.jinja`
- Create: `src/framework_cli/template/tests/unit/{{ 'test_graphql_router.py' if 'graphql' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing test**

Create `src/framework_cli/template/tests/unit/{{ 'test_graphql_router.py' if 'graphql' in batteries else '' }}.jinja`:

```python
"""GraphQL battery — the router factory logs the introspection/IDE decision (hermetic)."""

from {{ package_name }}.config.settings import get_settings
from {{ package_name }}.routes import graphql as graphql_routes


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def info(self, event: str, **kw: object) -> None:
        self.events.append((event, kw))


def test_configure_graphql_router_logs_toggle(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(graphql_routes, "get_logger", lambda: rec)

    graphql_routes._configure_graphql_router()

    logged = [kw for (event, kw) in rec.events if event == "graphql_ide_configured"]
    assert logged, "graphql_ide_configured was not logged at router construction"
    assert logged[0]["introspection_enabled"] == get_settings().resolved_graphql_ide
```

- [ ] **Step 2: Mirror + run to verify it fails**

```bash
rm -rf /tmp/oh-render && uv run framework template-render --out /tmp/oh-render >/dev/null
cp /tmp/oh-render/tests/unit/test_graphql_router.py /tmp/oh-work/tests/unit/test_graphql_router.py
(cd /tmp/oh-work && uv run pytest tests/unit/test_graphql_router.py -q)
```
Expected: FAIL — `AttributeError: module 'demo.routes.graphql' has no attribute 'get_logger'` (the module doesn't import get_logger yet; the `monkeypatch.setattr(..., raising=True)` errors) and `_configure_graphql_router` doesn't exist.

- [ ] **Step 3: Add the factory + log in routes/graphql.py**

Replace the body of `src/framework_cli/template/src/{{package_name}}/routes/{{ 'graphql.py' if 'graphql' in batteries else '' }}.jinja` with:

```python
from fastapi import APIRouter
from strawberry.fastapi import GraphQLRouter

from ..config.settings import get_settings
from ..graphql.context import get_context
from ..graphql.schema import build_schema
from ..logging_config import get_logger

router = APIRouter()


def _configure_graphql_router() -> GraphQLRouter:
    """Build the GraphQL router, logging the introspection/IDE decision.

    introspection is enabled iff the IDE is (disable_introspection=not ide), so a
    misconfigured prod that leaves the schema exposed is auditable from logs.
    """
    ide = get_settings().resolved_graphql_ide
    get_logger().info("graphql_ide_configured", introspection_enabled=ide)
    return GraphQLRouter(
        build_schema(disable_introspection=not ide),
        context_getter=get_context,
        graphql_ide="graphiql" if ide else None,
    )


router.include_router(_configure_graphql_router(), prefix="/graphql")
```

- [ ] **Step 4: Mirror + run to verify it passes (+ existing graphql tests)**

```bash
rm -rf /tmp/oh-render && uv run framework template-render --out /tmp/oh-render >/dev/null
cp /tmp/oh-render/src/demo/routes/graphql.py /tmp/oh-work/src/demo/routes/graphql.py
cp /tmp/oh-render/tests/unit/test_graphql_router.py /tmp/oh-work/tests/unit/test_graphql_router.py
(cd /tmp/oh-work && uv run pytest tests/unit/test_graphql_router.py tests/unit/test_graphql_metrics.py tests/functional/test_graphql.py -q)
```
Expected: PASS — the new toggle-log test, plus the existing graphql metrics + functional tests (the router still mounts at `/graphql` with the same schema/IDE behavior).

- [ ] **Step 5: Format check**

```bash
(cd /tmp/oh-render && uv run ruff format --check src/demo/routes/graphql.py tests/unit/test_graphql_router.py)
```
Expected: `... already formatted`.

- [ ] **Step 6: Commit**

Update CLAUDE.md pointer (brief), then:
```bash
git add CLAUDE.md \
  "src/framework_cli/template/src/{{package_name}}/routes/{{ 'graphql.py' if 'graphql' in batteries else '' }}.jinja" \
  "src/framework_cli/template/tests/unit/{{ 'test_graphql_router.py' if 'graphql' in batteries else '' }}.jinja"
git commit -m "feat(template): log the GraphQL introspection/IDE toggle at router construction"
```

---

## Task 3: Whole-slice verification

**Files:** none (verification only).

- [ ] **Step 1: Eval-fixture safety scan (expect broken: 0)**

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

- [ ] **Step 2: Full framework gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run mypy src
```
Expected: all pass, ruff clean, mypy clean. (These don't run the rendered-project tests — those were verified in Tasks 1-2 via the working project. The framework gate confirms the framework itself + the render/copier tests are unaffected.)

- [ ] **Step 3: Clean up**

```bash
rm -rf /tmp/oh-work /tmp/oh-render 2>/dev/null
rm -rf /tmp/pytest-of-chris/* 2>/dev/null
```

---

## Notes for the implementer

- **Windowed p99 is intentional** — p99 over the last `_MAX_LATENCY_SAMPLES` requests, not all-time. The existing `test_p99_latency` records only 100 samples (< 2048) so it's unaffected.
- `deque.append`/`deque.clear` are drop-in for the prior list calls — only `__init__` and the type hints change.
- The graphql factory preserves the exact prior behavior (same schema with `disable_introspection=not ide`, same `graphql_ide` value, same `/graphql` prefix) — it only adds the log + the testable seam.
- Keep `from ..logging_config import get_logger` at module level in `graphql.py` so the test can monkeypatch `graphql_routes.get_logger`.
