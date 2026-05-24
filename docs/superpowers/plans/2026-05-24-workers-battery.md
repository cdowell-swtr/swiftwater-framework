# Workers Battery (Plan 8c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone `workers` battery — Celery + Redis with a DB-backed dead-letter queue (delivering Plan 4's deferred DLQ), a beat scheduler whose example task is a heartbeat, full observability wiring, an additive webhooks composition, and a review-architecture heuristic.

**Architecture:** A battery-conditional `{{package_name}}/tasks/` package holding the Celery app, a base task whose `on_failure` drains exhausted tasks into a `dead_letter_tasks` table, an example task + heartbeat, and a beat schedule. Observability follows a formalized contract: task metrics via a `celery-exporter` scrape target, DLQ depth as a DB-backed gauge on the app's `/metrics`, container healthchecks, alert rules, and a Grafana panel. Workers is the first battery to conditionally render LOCKED infra files (`dev.yml`, `prometheus.yml`) and the first to inject into two hybrid managed sections (`.env.example`, `Taskfile.yml`); integrity stays green via the battery-aware `restore`/manifest machinery built in 8b/8a-2.

**Tech Stack:** Celery 5 (`celery[redis]`), Redis 7, SQLAlchemy/Alembic (existing DB layer), FastAPI, `celery-exporter` (container), Prometheus/Grafana/Alertmanager (existing stack), Copier (templating), pytest + testcontainers.

**Reference spec:** `docs/superpowers/specs/2026-05-24-workers-battery-design.md`. Read it for the full rationale; this plan is the executable decomposition.

---

## Conventions for every task

- **Framework tests** (in `tests/`) are written test-first against the **rendered** template — the render-assertion tests live in `tests/test_copier_runner.py`; the real-DB/real-Redis tests live in `tests/acceptance/test_rendered_project.py` (Docker-gated). Run framework tests with `uv run pytest`.
- **Generated-project test files** (`*.py.jinja` under `template/tests/`) are **payload**: they run inside a rendered project during acceptance (`scripts/coverage.sh`). Battery code must be covered by them (the rendered project's gate is ≥70% unit+functional).
- **Quality gate before every commit:** `uv run ruff check .` && `uv run mypy src` && the relevant `uv run pytest` subset. The template payload is NOT linted/typed as framework source (mypy excludes it).
- **Commit-gate hook:** `git commit` is blocked unless `CLAUDE.md` is staged. For task commits that don't change state narrative, still `git add CLAUDE.md` (bump nothing) is unnecessary — instead these task commits happen on the feature branch where the hook still applies, so each commit must `git add CLAUDE.md` only if changed; if the hook blocks, stage `CLAUDE.md` (unchanged) is not possible — **the controller bumps `CLAUDE.md` once at branch end**. During tasks, if the hook blocks a commit, the implementer should ask the controller. (In practice: the hook checks staged `CLAUDE.md`; coordinate per the existing project flow.)
- **Battery token:** `"workers"`. All conditional rendering keys on `"workers" in batteries`.
- **Conditional file/dir patterns** (Copier): a conditional directory is `{% if "workers" in batteries %}tasks{% endif %}/`; a conditional file is `{{ 'name.py' if 'workers' in batteries else '' }}.jinja` (empty basename → skipped). In-file conditionals use `{% if "workers" in batteries %}...{% endif %}`.

---

## File Structure

**New battery payload (rendered only when `workers` active):**
- `template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/__init__.py` — package marker.
- `.../tasks{% endif %}/app.py` — the Celery app + config.
- `.../tasks{% endif %}/base.py` — `BaseTask` (retry + `on_failure` → DLQ).
- `.../tasks{% endif %}/dead_letter.py` — `DeadLetterTask` model + repository + `render_dlq_metrics`.
- `.../tasks{% endif %}/liveness.py` — pure heartbeat write/staleness helpers.
- `.../tasks{% endif %}/tasks.py` — `process_async` example seam + `heartbeat` task.
- `.../tasks{% endif %}/schedule.py` — beat schedule registration.
- `template/migrations/versions/{{ '0003_dead_letter.py' if 'workers' in batteries else '' }}.jinja` — the DLQ migration.
- `template/infra/observability/prometheus/alerts/{{ 'workers_alerts.yml' if 'workers' in batteries else '' }}.jinja` — worker/beat/DLQ alerts (NEW, untracked).
- `template/infra/observability/grafana/dashboards/{{ 'workers.json' if 'workers' in batteries else '' }}.jinja` — workers dashboard (NEW, untracked).
- `template/tests/unit/{{ 'test_workers_unit.py' if 'workers' in batteries else '' }}.jinja` — generated unit tests (liveness, app config, base retry config).
- `template/tests/functional/{{ 'test_workers_functional.py' if 'workers' in batteries else '' }}.jinja` — generated functional tests (DLQ on_failure, DLQ gauge, /health worker).

**Modified (conditional content added):**
- `template/src/{{package_name}}/config/settings.py.jinja` — `celery_broker_url`/`celery_result_backend`/`redis_url` fields (NOT tracked).
- `template/.env.example.jinja` — `APP_CELERY_*` lines in the managed section (HYBRID — second injection).
- `template/Taskfile.yml.jinja` — `worker`/`beat` tasks in the managed section (HYBRID — second injection).
- `template/migrations/env.py.jinja` — conditional import of the DLQ model.
- `template/src/{{package_name}}/routes/health.py.jinja` — DLQ gauge on `/metrics`, worker liveness on `/health`, SLO per-instance comment (NOT tracked).
- `template/infra/compose/dev.yml.jinja` — `redis`/`worker`/`beat`/`celery-exporter` services + `app` depends_on + `redisdata` volume (LOCKED — conditional content; byte-identical without battery).
- `template/infra/observability/prometheus/prometheus.yml` → **rename to** `prometheus.yml.jinja` — conditional `celery-exporter` scrape job (LOCKED — byte-identical without battery).
- `template/pyproject.toml.jinja` — `celery[redis]` in dependencies (gated; pyproject is intentionally untracked).
- `template/src/{{package_name}}/{% if "webhooks" in batteries %}webhooks{% endif %}/handler.py` — conditional enqueue when both batteries present.
- `src/framework_cli/batteries.py` — register `workers`.
- `src/framework_cli/review/agents/architecture.md` — the heavy-inline heuristic.
- `tests/eval/fixtures/architecture/{bad,good}/...` — one new fixture pair.

---

### Task 1: Register the `workers` battery + runtime dependency

**Files:**
- Modify: `src/framework_cli/batteries.py:14-21`
- Modify: `src/framework_cli/template/pyproject.toml.jinja:5-18`
- Test: `tests/test_batteries.py` (add), `tests/test_copier_runner.py` (add)

- [ ] **Step 1: Write the failing framework test (registry)**

In `tests/test_batteries.py` add:

```python
def test_workers_battery_is_registered():
    from framework_cli.batteries import get_battery, resolve
    spec = get_battery("workers")
    assert spec.name == "workers"
    assert spec.requires == ()          # standalone — depends on nothing
    assert resolve(["workers"]) == ["workers"]
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `uv run pytest tests/test_batteries.py::test_workers_battery_is_registered -v`
Expected: FAIL (`KeyError: unknown battery: workers`).

- [ ] **Step 3: Register the battery**

In `src/framework_cli/batteries.py`, add to `_BATTERIES`:

```python
    "workers": BatterySpec(
        "workers",
        "Celery + Redis async task workers with a DB-backed dead-letter queue and beat scheduler",
    ),
```

- [ ] **Step 4: Run the test, confirm it passes**

Run: `uv run pytest tests/test_batteries.py::test_workers_battery_is_registered -v`
Expected: PASS.

- [ ] **Step 5: Write the failing render test (dependency)**

In `tests/test_copier_runner.py` add (use the file's existing render helper — match the `test_render_with_webhooks_battery` pattern at line ~918):

```python
def test_render_with_workers_battery_adds_celery_dep(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])   # match the helper used by webhooks tests
    pyproject = (dest / "pyproject.toml").read_text()
    assert "celery[redis]" in pyproject

def test_render_without_workers_battery_has_no_celery_dep(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    assert "celery[redis]" not in (dest / "pyproject.toml").read_text()
```

> Note: copy the exact render-helper call used by `test_render_with_webhooks_battery`; if it inlines `run_copy(... data={"batteries": [...]})`, do the same here.

- [ ] **Step 6: Run, confirm fail; add the dependency; run, confirm pass**

In `pyproject.toml.jinja` dependencies array, after `"pybreaker>=1.2",`:

```jinja
{% if "workers" in batteries %}    "celery[redis]>=5.4",
{% endif %}
```

Run: `uv run pytest tests/test_copier_runner.py -k workers -v` → PASS. Then `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/batteries.py src/framework_cli/template/pyproject.toml.jinja tests/test_batteries.py tests/test_copier_runner.py
git commit -m "feat(workers): register the workers battery + celery[redis] dependency"
```

---

### Task 2: The Celery app

**Files:**
- Create: `template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/__init__.py`
- Create: `template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/app.py`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

```python
def test_render_workers_creates_tasks_package(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    assert (dest / "src" / PKG / "tasks" / "app.py").exists()
    assert (dest / "src" / PKG / "tasks" / "__init__.py").exists()

def test_render_no_tasks_package_without_workers(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    assert not (dest / "src" / PKG / "tasks").exists()
```

> `PKG` = the rendered package name the other tests use (e.g. derived from the project slug); reuse the existing test constant.

- [ ] **Step 2: Run, confirm fail** (`uv run pytest tests/test_copier_runner.py -k tasks_package -v` → FAIL).

- [ ] **Step 3: Create the package marker** (`.../tasks{% endif %}/__init__.py`):

```python
"""Async task workers (Celery). Edit tasks.py and schedule.py; the rest is framework wiring."""
```

- [ ] **Step 4: Create `app.py`**

```python
"""The Celery application. Broker + result backend come from settings (Redis).

Workers run in their own process (see the `worker`/`beat` compose services). Task-level
metrics are exposed by the `celery-exporter` sidecar — a separate Prometheus scrape target —
not through the FastAPI app. The only worker metric on the app's /metrics is DLQ depth
(a DB count), because the dead-letter table is the shared source of truth.
"""

from __future__ import annotations

from celery import Celery

from ..config.settings import get_settings

_settings = get_settings()

app = Celery(
    "{{ package_name }}",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["{{ package_name }}.tasks.tasks"],
)

app.conf.update(
    task_acks_late=True,                # a task re-runs if a worker dies mid-flight
    task_reject_on_worker_lost=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_default_queue="{{ package_name }}",
)

# Register the beat schedule (periodic tasks).
from .schedule import register_schedule  # noqa: E402  (avoid a circular import at module top)

register_schedule(app)
```

> `schedule.py` and `tasks.py` arrive in Task 6 — this module references them but they render in the same battery, so the rendered package is internally complete. The render test here only asserts the file exists; import-time correctness is proven in the acceptance task.

- [ ] **Step 5: Run the render test, confirm pass.**

- [ ] **Step 6: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/{% if \"workers\" in batteries %}tasks{% endif %}" tests/test_copier_runner.py
git commit -m "feat(workers): Celery app module"
```

---

### Task 3: Dead-letter model, migration, and metadata import

**Files:**
- Create: `template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/dead_letter.py` (model only this task; repository in Task 4)
- Create: `template/migrations/versions/{{ '0003_dead_letter.py' if 'workers' in batteries else '' }}.jinja`
- Modify: `template/migrations/env.py.jinja:6-8`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render tests (migration ordering)**

```python
def test_render_workers_migration_chains_off_initial(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    mig = (dest / "migrations" / "versions" / "0003_dead_letter.py").read_text()
    assert 'revision = "0003"' in mig
    assert 'down_revision = "0001"' in mig

def test_render_workers_migration_chains_off_webhooks(tmp_path: Path):
    dest = _render(tmp_path, batteries=["webhooks", "workers"])
    mig = (dest / "migrations" / "versions" / "0003_dead_letter.py").read_text()
    assert 'down_revision = "0002"' in mig

def test_render_no_workers_migration_without_battery(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    assert not (dest / "migrations" / "versions" / "0003_dead_letter.py").exists()
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Create the model** (`.../tasks{% endif %}/dead_letter.py`):

```python
"""The dead-letter queue: tasks that exhausted their retries land here (durable, queryable).

This is the terminal sink Plan 4's `retries_exhausted` recoverability metric anticipated.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class DeadLetterTask(Base):
    """One row per task that failed terminally (after retries)."""

    __tablename__ = "dead_letter_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    args_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    traceback: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 4: Create the migration** (`.../versions/{{ '0003_dead_letter.py' ... }}.jinja`):

```jinja
"""dead-letter queue

Revision ID: 0003
Revises: {{ '0002' if 'webhooks' in batteries else '0001' }}

"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "{{ '0002' if 'webhooks' in batteries else '0001' }}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dead_letter_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("args_json", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=False),
        sa.Column(
            "failed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("dead_letter_tasks")
```

- [ ] **Step 5: Add the conditional metadata import** in `migrations/env.py.jinja` (after the webhooks import line 7):

```jinja
{% if "workers" in batteries %}from {{ package_name }}.tasks import dead_letter as _dead_letter_models  # noqa: F401
{% endif %}
```

- [ ] **Step 6: Run the render tests, confirm pass.** Then a render of `batteries=[]` must leave `env.py` import-free of workers — add:

```python
def test_render_env_py_no_workers_import_without_battery(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    assert "tasks import dead_letter" not in (dest / "migrations" / "env.py").read_text()
```

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py
git commit -m "feat(workers): dead_letter model + 0003 migration (down_revision chains off webhooks when present)"
```

---

### Task 4: Dead-letter repository + DLQ metrics renderer

**Files:**
- Modify: `template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/dead_letter.py`
- Create: `template/tests/functional/{{ 'test_workers_functional.py' if 'workers' in batteries else '' }}.jinja` (start it here; extended in later tasks)
- Test: covered by the generated functional test (run under acceptance, Task 13)

- [ ] **Step 1: Add the repository + metrics renderer** to `dead_letter.py`:

```python
from sqlalchemy import func as _sql_func, select
from sqlalchemy.orm import Session


def record_failure(
    session: Session, *, task_name: str, task_id: str, args_json: str, traceback: str
) -> None:
    """Persist a terminally-failed task. Commits its own transaction (called from on_failure)."""
    session.add(
        DeadLetterTask(
            task_name=task_name, task_id=task_id, args_json=args_json, traceback=traceback
        )
    )
    session.commit()


def count(session: Session) -> int:
    return int(session.scalar(select(_sql_func.count()).select_from(DeadLetterTask)) or 0)


def list_recent(session: Session, limit: int = 50) -> list[DeadLetterTask]:
    return list(
        session.scalars(select(DeadLetterTask).order_by(DeadLetterTask.id.desc()).limit(limit))
    )


def render_dlq_metrics(session: Session) -> str:
    """Prometheus exposition for DLQ depth — appended to the app's /metrics (DB is shared truth)."""
    return (
        "# HELP app_dead_letter_tasks Tasks in the dead-letter queue (terminal failures)\n"
        "# TYPE app_dead_letter_tasks gauge\n"
        f"app_dead_letter_tasks {count(session)}\n"
    )
```

- [ ] **Step 2: Start the generated functional test** (`template/tests/functional/{{ 'test_workers_functional.py' ... }}.jinja`). This file runs **inside a rendered project** against testcontainers Postgres (match the webhooks functional test's session fixture — reuse whatever `db_session`/`engine` fixture the generated `tests/functional/conftest.py` already provides):

```jinja
"""Workers battery — functional tests (real Postgres via the project's test fixtures)."""

import json

from {{ package_name }}.tasks import dead_letter


def test_record_failure_and_count(db_session):
    assert dead_letter.count(db_session) == 0
    dead_letter.record_failure(
        db_session, task_name="t", task_id="abc", args_json=json.dumps([1, 2]), traceback="boom"
    )
    assert dead_letter.count(db_session) == 1
    assert dead_letter.list_recent(db_session)[0].task_name == "t"


def test_render_dlq_metrics_reports_depth(db_session):
    out = dead_letter.render_dlq_metrics(db_session)
    assert "app_dead_letter_tasks" in out
    assert out.strip().endswith("0")
```

> Inspect the generated `tests/functional/conftest.py` (shipped by Plan 3c) for the exact session fixture name; align the parameter (`db_session` here) to it. If the project's fixture yields a `Session` per test with a created schema, this works as written.

- [ ] **Step 3: Verify framework suite still green** (these generated tests don't run in the framework suite; they run under acceptance Task 13). Run `uv run pytest tests/test_copier_runner.py -k workers -v` and `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 4: Commit**

```bash
git add src/framework_cli/template
git commit -m "feat(workers): dead-letter repository + DLQ-depth metrics renderer + functional test scaffold"
```

---

### Task 5: Base task — retry + on_failure → DLQ

**Files:**
- Create: `template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/base.py`
- Modify: `template/tests/functional/{{ 'test_workers_functional.py' ... }}.jinja`

- [ ] **Step 1: Create `base.py`**

```python
"""The base task: bounded retry, and on terminal failure a row in the dead-letter queue.

Every task should inherit from BaseTask (the `tasks.py` example does) so failures are captured.
"""

from __future__ import annotations

import json
from typing import Any

import celery

from ..db.engine import SessionLocal
from . import dead_letter


class BaseTask(celery.Task):
    # Bounded retry with exponential backoff + jitter (Plan 4 recoverability discipline).
    autoretry_for = (Exception,)
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    def on_failure(
        self, exc: Exception, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], einfo: Any
    ) -> None:
        """Called once retries are exhausted — drain to the dead-letter queue."""
        with SessionLocal() as session:
            dead_letter.record_failure(
                session,
                task_name=self.name or "unknown",
                task_id=task_id,
                args_json=json.dumps(list(args), default=str),
                traceback=str(einfo),
            )
```

- [ ] **Step 2: Add the generated functional test** for the DLQ-on-failure path (append to `test_workers_functional.py.jinja`). It uses Celery **eager** mode so the task + `on_failure` run inline and deterministically:

```jinja
def test_failing_task_lands_in_dead_letter_queue(db_session, monkeypatch):
    from {{ package_name }}.tasks.app import app as celery_app
    from {{ package_name }}.tasks.base import BaseTask
    from {{ package_name }}.tasks import dead_letter as dl

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False  # let on_failure fire instead of raising

    @celery_app.task(base=BaseTask, bind=True, max_retries=0, name="always_fails")
    def always_fails(self):
        raise ValueError("boom")

    always_fails.delay()

    # on_failure opened its own session; assert via a fresh count
    assert dl.count(db_session) >= 1
    row = dl.list_recent(db_session)[0]
    assert row.task_name == "always_fails"
    assert "boom" in row.traceback
```

> If the project's `db_session` fixture wraps a transaction that `on_failure`'s separate session won't see, adjust the assertion to open a new session via `SessionLocal()` (import from `{{ package_name }}.db.engine`). The acceptance run (Task 13) is the real gate; align the fixture semantics there.

- [ ] **Step 3: Render-test that `base.py` renders** (framework suite):

```python
def test_render_workers_creates_base_task(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    assert (dest / "src" / PKG / "tasks" / "base.py").exists()
```

Run `uv run pytest tests/test_copier_runner.py -k workers -v` → PASS; `ruff`/`mypy` clean.

- [ ] **Step 4: Commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py
git commit -m "feat(workers): BaseTask with bounded retry + on_failure draining to the DLQ"
```

---

### Task 6: Liveness helpers, example task, heartbeat, beat schedule

**Files:**
- Create: `template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/liveness.py`
- Create: `template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/tasks.py`
- Create: `template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/schedule.py`
- Create: `template/tests/unit/{{ 'test_workers_unit.py' if 'workers' in batteries else '' }}.jinja`

- [ ] **Step 1: Create `liveness.py`** (pure, client-agnostic — testable with a dict fake, no real Redis):

```python
"""Worker liveness via a heartbeat marker in Redis. Pure helpers so /health and the beat task
share one definition of 'alive' and unit tests need no broker.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

HEARTBEAT_KEY = "{{ package_name }}:worker:heartbeat"
MAX_AGE_SECONDS = 90  # stale if no beat tick within this window (beat runs every 30s)


class _KV(Protocol):
    def get(self, key: str) -> bytes | str | None: ...
    def set(self, key: str, value: str) -> object: ...


def write_heartbeat(client: _KV, *, now: datetime | None = None) -> None:
    client.set(HEARTBEAT_KEY, (now or datetime.now(timezone.utc)).isoformat())


def is_alive(client: _KV, *, now: datetime | None = None, max_age: int = MAX_AGE_SECONDS) -> bool:
    raw = client.get(HEARTBEAT_KEY)
    if raw is None:
        return False
    stamp = raw.decode() if isinstance(raw, bytes) else raw
    last = datetime.fromisoformat(stamp)
    reference = now or datetime.now(timezone.utc)
    return (reference - last).total_seconds() <= max_age
```

- [ ] **Step 2: Create `tasks.py`** (the builder seam + the heartbeat):

```python
"""Your async tasks. `process_async` is the example seam — replace it. `heartbeat` feeds the
worker liveness marker /health reads; keep it.
"""

from __future__ import annotations

import redis

from ..config.settings import get_settings
from . import liveness
from .app import app
from .base import BaseTask


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


@app.task(base=BaseTask, bind=True)
def process_async(self, payload: dict) -> None:
    """Example background task. REPLACE with your logic. Failures (after retries) go to the DLQ."""
    # do the slow/heavy work here, off the request path
    return None


@app.task(bind=True)
def heartbeat(self) -> None:
    """Periodic liveness tick (registered in schedule.py). Writes the marker /health checks."""
    liveness.write_heartbeat(_redis_client())
```

- [ ] **Step 3: Create `schedule.py`**:

```python
"""Beat schedule. Add periodic tasks here. The heartbeat is wired by default."""

from __future__ import annotations

from celery import Celery


def register_schedule(app: Celery) -> None:
    app.conf.beat_schedule = {
        "worker-heartbeat": {
            "task": "{{ package_name }}.tasks.tasks.heartbeat",
            "schedule": 30.0,  # seconds
        },
    }
```

- [ ] **Step 4: Create the generated unit test** (`template/tests/unit/{{ 'test_workers_unit.py' ... }}.jinja`) — hermetic, dict-fake client, no Redis/broker:

```jinja
"""Workers battery — unit tests (hermetic; no broker/DB)."""

from datetime import datetime, timedelta, timezone

from {{ package_name }}.tasks import liveness


class _FakeKV:
    def __init__(self):
        self._d = {}
    def get(self, key):
        return self._d.get(key)
    def set(self, key, value):
        self._d[key] = value


def test_heartbeat_roundtrip_is_alive():
    kv = _FakeKV()
    now = datetime(2026, 5, 24, tzinfo=timezone.utc)
    liveness.write_heartbeat(kv, now=now)
    assert liveness.is_alive(kv, now=now + timedelta(seconds=10)) is True


def test_stale_heartbeat_is_not_alive():
    kv = _FakeKV()
    now = datetime(2026, 5, 24, tzinfo=timezone.utc)
    liveness.write_heartbeat(kv, now=now)
    assert liveness.is_alive(kv, now=now + timedelta(seconds=600)) is False


def test_missing_heartbeat_is_not_alive():
    assert liveness.is_alive(_FakeKV()) is False


def test_celery_app_config_is_safe():
    from {{ package_name }}.tasks.app import app
    assert app.conf.task_acks_late is True
    assert app.conf.task_serializer == "json"
```

- [ ] **Step 5: Render test (framework)** that all three modules render:

```python
def test_render_workers_creates_task_modules(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    base = dest / "src" / PKG / "tasks"
    for name in ("liveness.py", "tasks.py", "schedule.py"):
        assert (base / name).exists()
```

Run `uv run pytest tests/test_copier_runner.py -k workers -v` → PASS; `ruff`/`mypy` clean.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py
git commit -m "feat(workers): liveness helpers, example task, heartbeat, beat schedule"
```

---

### Task 7: Settings + `.env.example` + `Taskfile` managed-section injection

**Files:**
- Modify: `template/src/{{package_name}}/config/settings.py.jinja:29-33`
- Modify: `template/.env.example.jinja:13-16`
- Modify: `template/Taskfile.yml.jinja` (inside the managed section, near `db:migrate`)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write failing render tests**

```python
def test_render_workers_settings_fields(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    s = (dest / "src" / PKG / "config" / "settings.py").read_text()
    assert "celery_broker_url" in s and "redis_url" in s

def test_render_workers_env_lines_in_managed_section(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    env = (dest / ".env.example").read_text()
    begin = env.index("FRAMEWORK:BEGIN"); end = env.index("FRAMEWORK:END")
    assert "APP_CELERY_BROKER_URL" in env[begin:end]

def test_render_no_celery_env_without_workers(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    assert "APP_CELERY_BROKER_URL" not in (dest / ".env.example").read_text()

def test_render_workers_taskfile_has_worker_task(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    tf = (dest / "Taskfile.yml").read_text()
    begin = tf.index("FRAMEWORK:BEGIN"); end = tf.index("FRAMEWORK:END")
    assert "worker:" in tf[begin:end]
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Settings fields** — in `settings.py.jinja`, after the webhooks block (line 33, before `@property`):

```jinja
{% if "workers" in batteries %}
    # Celery workers (Redis broker + result backend).
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
{% endif %}
```

- [ ] **Step 4: `.env.example` managed-section lines** — in `.env.example.jinja`, after the webhooks block (line 15, before `# FRAMEWORK:END`):

```jinja
{% if "workers" in batteries %}# Celery workers: Redis broker + result backend (in-network defaults; override per environment).
APP_REDIS_URL=redis://redis:6379/0
APP_CELERY_BROKER_URL=redis://redis:6379/0
APP_CELERY_RESULT_BACKEND=redis://redis:6379/1
{% endif %}
```

> This is the **second** hybrid managed-section injection (after webhooks). The integrity coupling is already handled by 8b (`new` checksums the active section; `upskill --with` regenerates; `restore` is battery-aware) and 8a-2 (`downskill` re-renders the section + regenerates). No new integrity code.

- [ ] **Step 5: Taskfile tasks** — in `Taskfile.yml.jinja`, **inside the managed section** (e.g. right after the `db:migrate`/`db:seed` block, before `# FRAMEWORK:END`):

```jinja
{% if "workers" in batteries %}
  worker:
    desc: Run a Celery worker locally (the dev compose runs one already in `task dev`).
    cmds:
      - uv run celery -A {{ package_name }}.tasks.app worker --loglevel=info

  beat:
    desc: Run the Celery beat scheduler locally.
    cmds:
      - uv run celery -A {{ package_name }}.tasks.app beat --loglevel=info
{% endif %}
```

> Placed **inside** the managed section (not below `FRAMEWORK:END`) so `framework downskill workers` removes them via the hybrid section re-render — this corrects the spec's "below FRAMEWORK:END" note, which would have leaked on downskill.

- [ ] **Step 6: Run the render tests, confirm pass.** Add a no-battery byte-stability check:

```python
def test_render_taskfile_unchanged_without_workers(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    assert "worker:" not in (dest / "Taskfile.yml").read_text()
```

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py
git commit -m "feat(workers): settings + .env.example + Taskfile managed-section injection"
```

---

### Task 8: `/metrics` DLQ gauge + `/health` worker liveness + SLO comment

**Files:**
- Modify: `template/src/{{package_name}}/routes/health.py.jinja`
- Modify: `template/tests/functional/{{ 'test_workers_functional.py' ... }}.jinja`

- [ ] **Step 1: Edit `health.py.jinja`** — add the SLO per-instance comment (always), and gated workers blocks:

Replace the `/health` and `/metrics` handlers with:

```jinja
@router.get("/health")
def health(request: Request) -> JSONResponse:
    """Readiness + SLO status. Returns 200 with the structured SLO report.

    NOTE: the SLO figures are computed from THIS instance's in-process metrics — a per-instance
    judgement, correct for a load-balancer probe. The fleet-wide SLO view lives in Grafana
    (Prometheus aggregates every instance's /metrics), not here.
    """
    report = build_health_report(request.app.state.metrics, request.app.state.settings)
{% if "workers" in batteries %}
    import redis as _redis

    from {{ package_name }}.tasks import liveness as _liveness

    _client = _redis.Redis.from_url(request.app.state.settings.redis_url)
    try:
        report["workers"] = {"alive": _liveness.is_alive(_client)}
    except Exception:  # broker unreachable — report degraded, never 500 the probe
        report["workers"] = {"alive": False}
{% endif %}
    return JSONResponse(report, status_code=200)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request) -> PlainTextResponse:
    """Prometheus exposition format from the in-process registry."""
    body = (
        request.app.state.metrics.render_prometheus()
        + recoverability.render_prometheus()
    )
{% if "workers" in batteries %}
    from {{ package_name }}.db.engine import SessionLocal
    from {{ package_name }}.tasks import dead_letter as _dead_letter

    with SessionLocal() as _session:
        body += _dead_letter.render_dlq_metrics(_session)
{% endif %}
    return PlainTextResponse(
        body,
        status_code=200,
        media_type="text/plain; version=0.0.4",
    )
```

- [ ] **Step 2: Add the generated functional tests** (append to `test_workers_functional.py.jinja`) — these run against the rendered app + testcontainers Postgres:

```jinja
def test_metrics_endpoint_exposes_dlq_gauge(client):
    body = client.get("/metrics").text
    assert "app_dead_letter_tasks" in body


def test_health_reports_workers_block(client):
    report = client.get("/health").json()
    assert "workers" in report
    assert "alive" in report["workers"]
```

> Use the project's existing FastAPI `TestClient` fixture (`client`) from `tests/functional/conftest.py`. `is_alive` will be `False` (no beat running in tests) — the assertion only checks the block exists, which is the contract.

- [ ] **Step 3: Render test (framework)** that the gauge wiring is present with the battery and absent without:

```python
def test_render_health_has_dlq_gauge_with_workers(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    h = (dest / "src" / PKG / "routes" / "health.py").read_text()
    assert "render_dlq_metrics" in h and "per-instance" in h

def test_render_health_clean_without_workers(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    h = (dest / "src" / PKG / "routes" / "health.py").read_text()
    assert "render_dlq_metrics" not in h
    assert "per-instance" in h   # the SLO comment is unconditional
```

Run the render tests → PASS; `ruff`/`mypy` clean.

- [ ] **Step 4: Commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py
git commit -m "feat(workers): DLQ-depth gauge on /metrics, worker liveness on /health, per-instance SLO note"
```

---

### Task 9: Dev-compose services (redis, worker, beat, celery-exporter)

**Files:**
- Modify: `template/infra/compose/dev.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write failing render tests**

```python
def test_render_workers_compose_services(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    for svc in ("redis:", "worker:", "beat:", "celery-exporter:"):
        assert svc in dev
    assert "redisdata:" in dev

def test_render_compose_byte_identical_without_workers(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "redis:" not in dev and "celery-exporter:" not in dev
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Add gated services** to `dev.yml.jinja`. Add `depends_on: redis` to the `app` service conditionally, and append the services before the `volumes:` block. Worker/beat reuse the app source bind-mount so code reloads in dev:

```jinja
{% if "workers" in batteries %}
  redis:
    image: redis:7-alpine
    profiles: ["dev", "lite"]
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - "redisdata:/data"

  worker:
    profiles: ["dev"]
    command: ["celery", "-A", "{{ package_name }}.tasks.app", "worker", "--loglevel=info"]
    working_dir: /app
    environment:
      PYTHONPATH: /app/src
      APP_REDIS_URL: "redis://redis:6379/0"
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
      APP_DATABASE_URL: "postgresql+psycopg://app:app@postgres:5432/app"
    volumes:
      - ../../src:/app/src
    healthcheck:
      test: ["CMD", "celery", "-A", "{{ package_name }}.tasks.app", "inspect", "ping", "-d", "celery@$$HOSTNAME"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 20s
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy

  beat:
    profiles: ["dev"]
    command: ["celery", "-A", "{{ package_name }}.tasks.app", "beat", "--loglevel=info"]
    working_dir: /app
    environment:
      PYTHONPATH: /app/src
      APP_REDIS_URL: "redis://redis:6379/0"
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
    volumes:
      - ../../src:/app/src
    depends_on:
      redis:
        condition: service_healthy

  celery-exporter:
    image: danihodovic/celery-exporter:0.10.5
    profiles: ["dev"]
    command: ["--broker-url=redis://redis:6379/0"]
    ports:
      - "9808:9808"
    depends_on:
      redis:
        condition: service_healthy
{% endif %}
```

The `worker`/`beat`/`celery-exporter` use the default service image only if one is set; since the base `app` builds from the Dockerfile, give worker/beat the same build. **Add `build`/`image` consistent with how `app` is defined in `base.yml`** — inspect `infra/compose/base.yml` and mirror the `app` service's `build:`/`image:` keys onto `worker` and `beat` (they run the same codebase). If `app` uses `build: {context: ../.., dockerfile: infra/docker/Dockerfile}`, add the identical block to `worker` and `beat`.

- [ ] **Step 4: Run the render tests, confirm pass.**

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/infra/compose/dev.yml.jinja tests/test_copier_runner.py
git commit -m "feat(workers): redis/worker/beat/celery-exporter dev-compose services"
```

---

### Task 10: Prometheus scrape target + workers alerts + Grafana dashboard

**Files:**
- Rename: `template/infra/observability/prometheus/prometheus.yml` → `prometheus.yml.jinja`, add a conditional scrape job
- Create: `template/infra/observability/prometheus/alerts/{{ 'workers_alerts.yml' if 'workers' in batteries else '' }}.jinja`
- Create: `template/infra/observability/grafana/dashboards/{{ 'workers.json' if 'workers' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write failing render tests**

```python
def test_render_workers_prometheus_scrape(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    prom = (dest / "infra" / "observability" / "prometheus" / "prometheus.yml").read_text()
    assert "celery-exporter" in prom

def test_render_prometheus_unchanged_without_workers(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    prom = (dest / "infra" / "observability" / "prometheus" / "prometheus.yml").read_text()
    assert "celery-exporter" not in prom
    # the two baseline jobs remain exactly
    assert "job_name: app" in prom and "job_name: prometheus" in prom

def test_render_workers_alerts_and_dashboard(tmp_path: Path):
    dest = _render(tmp_path, batteries=["workers"])
    assert (dest / "infra" / "observability" / "prometheus" / "alerts" / "workers_alerts.yml").exists()
    assert (dest / "infra" / "observability" / "grafana" / "dashboards" / "workers.json").exists()

def test_render_no_workers_alerts_without_battery(tmp_path: Path):
    dest = _render(tmp_path, batteries=[])
    assert not (dest / "infra" / "observability" / "prometheus" / "alerts" / "workers_alerts.yml").exists()
```

- [ ] **Step 2: Rename + edit prometheus config.** `git mv` the file to add `.jinja`, then append a gated scrape job after the `prometheus` job:

```bash
git mv "src/framework_cli/template/infra/observability/prometheus/prometheus.yml" \
       "src/framework_cli/template/infra/observability/prometheus/prometheus.yml.jinja"
```

Append to `prometheus.yml.jinja` (after the `localhost:9090` job; **the no-workers render must be byte-identical** to the original, so add nothing but the gated block at the end):

```jinja
{% if "workers" in batteries %}  - job_name: celery
    static_configs:
      - targets: ["celery-exporter:9808"]
{% endif %}
```

> Verify byte-identity: the file content before the `{% if %}` must match the original exactly (no trailing-whitespace changes). The `test_render_prometheus_unchanged_without_workers` test guards this. `prometheus.yml` is LOCKED_TRACKED — the rendered path is unchanged, so `framework integrity` keys on it correctly; a workers project records the scrape-job-included checksum at `new` time (Task 13 verifies green).

- [ ] **Step 3: Create `workers_alerts.yml.jinja`** (rendered to `workers_alerts.yml`; Prometheus globs `alerts/*.yml`):

```jinja
groups:
- name: workers
  rules:
  - alert: DeadLetterQueueNonEmpty
    expr: app_dead_letter_tasks > 0
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: Tasks have landed in the dead-letter queue ({{ '{{' }} $value {{ '}}' }} total)
  - alert: CeleryWorkerDown
    expr: up{job="celery"} == 0
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: No Celery worker is being scraped (celery-exporter target down)
  - alert: CeleryTaskFailuresHigh
    expr: increase(celery_task_failed_total[5m]) > 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: Celery task failures observed in the last 5m
```

> The `{{ '{{' }}`/`{{ '}}' }}` escaping emits literal Prometheus `{{ $value }}` templating through Jinja. Confirm the rendered file contains `{{ $value }}`.

- [ ] **Step 4: Create `workers.json.jinja`** — a minimal valid Grafana dashboard with three panels (DLQ depth, task rates, worker-up). Keep it small but valid JSON. Base it on the structure of the existing `slo.json` (read it first for the schema version + panel shape) and include panels querying `app_dead_letter_tasks`, `rate(celery_task_succeeded_total[5m])` / `rate(celery_task_failed_total[5m])`, and `up{job="celery"}`. Title: `"Workers"`, `uid: "workers"`.

- [ ] **Step 5: Run the render tests, confirm pass.**

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py
git commit -m "feat(workers): prometheus celery scrape target + workers alerts + grafana dashboard"
```

---

### Task 11: Webhooks composition (enqueue when both batteries present)

**Files:**
- Modify: `template/src/{{package_name}}/{% if "webhooks" in batteries %}webhooks{% endif %}/handler.py`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write failing render tests**

```python
def test_render_webhooks_alone_handler_is_inline(tmp_path: Path):
    dest = _render(tmp_path, batteries=["webhooks"])
    h = (dest / "src" / PKG / "webhooks" / "handler.py").read_text()
    assert "process_async" not in h
    assert "get_logger().info" in h          # 8b inline behaviour preserved

def test_render_webhooks_plus_workers_handler_enqueues(tmp_path: Path):
    dest = _render(tmp_path, batteries=["webhooks", "workers"])
    h = (dest / "src" / PKG / "webhooks" / "handler.py").read_text()
    assert "process_async.delay" in h
```

- [ ] **Step 2: Run, confirm fail** (currently `handler.py` is not a `.jinja`, so it renders verbatim with no conditional). **Rename it to a templated path** so Copier renders it:

```bash
git mv "src/framework_cli/template/src/{{package_name}}/{% if \"webhooks\" in batteries %}webhooks{% endif %}/handler.py" \
       "src/framework_cli/template/src/{{package_name}}/{% if \"webhooks\" in batteries %}webhooks{% endif %}/handler.py.jinja"
```

> Verify the file currently has no `{{ }}`; after renaming to `.jinja`, plain `{` in the body (none here) would need care — this file is pure Python with no braces, safe.

- [ ] **Step 3: Edit `handler.py.jinja`** to the conditional form:

```jinja
"""The builder seam: replace `handle_event` with your webhook logic.

Keep it FAST — this runs inline in the request unless the workers battery is present, in which
case it dispatches to a Celery task (the robust path). Heavy/slow work belongs off the request
path either way.
"""

from __future__ import annotations
{% if "workers" in batteries %}
from ..tasks.tasks import process_async


def handle_event(event: dict) -> None:
    """Hand the verified, de-duplicated event to a background worker (fast return)."""
    process_async.delay(event)
{% else %}
from ..logging_config import get_logger


def handle_event(event: dict) -> None:
    """Process a verified, de-duplicated webhook event. REPLACE THIS with your logic."""
    get_logger().info("webhook_event", event_type=event.get("type", "unknown"))
{% endif %}
```

- [ ] **Step 4: Run the render tests, confirm pass.** Also re-run the webhooks render tests to confirm 8b behaviour is byte-stable for webhooks-alone:

Run: `uv run pytest tests/test_copier_runner.py -k "webhooks or workers" -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py
git commit -m "feat(workers): webhooks handler enqueues to a worker when both batteries present"
```

---

### Task 12: Review-architecture heuristic + eval fixture

**Files:**
- Modify: `src/framework_cli/review/agents/architecture.md`
- Create: `tests/eval/fixtures/architecture/bad/heavy-inline-handler.diff` + `.expect.json`
- Create: `tests/eval/fixtures/architecture/good/lightweight-handler.diff`

- [ ] **Step 1: Extend the agent prompt.** Append to `architecture.md`:

```text
Also flag HEAVY synchronous work inside a request handler / webhook handler — external HTTP
calls, large or long-running DB writes, time.sleep, or loops over remote I/O — that blocks the
response. Recommend moving it to a background worker: the `workers` battery
(`framework upskill --with workers`), dispatching from the handler seam. If a `tasks/` package is
already present, recommend dispatching to it rather than running inline. Do NOT flag lightweight
inline handlers (a quick log, a single small insert) — only genuinely heavy/blocking work. Such a
finding is "high".
```

- [ ] **Step 2: Create the "bad" fixture** `tests/eval/fixtures/architecture/bad/heavy-inline-handler.diff` (a webhook handler doing obvious heavy inline work):

```diff
--- a/src/app/webhooks/handler.py
+++ b/src/app/webhooks/handler.py
@@ -1,3 +1,18 @@
+import time
+
+import httpx
+
+from app.db.engine import SessionLocal
+from app.db.repository import bulk_insert
+
+
+def handle_event(event: dict) -> None:
+    """Process a verified webhook event."""
+    # call three external services synchronously, in the request path
+    for url in event["callbacks"]:
+        httpx.post(url, json=event, timeout=30)
+    with SessionLocal() as session:
+        bulk_insert(session, event["rows"])  # large write
+    time.sleep(5)  # wait for downstream to settle
```

- [ ] **Step 3: Create its expectation** `heavy-inline-handler.expect.json`:

```json
{"file": "src/app/webhooks/handler.py"}
```

- [ ] **Step 4: Create the "good" fixture** `tests/eval/fixtures/architecture/good/lightweight-handler.diff` (a legitimate lightweight inline handler — no finding expected; good fixtures have no `.expect.json`):

```diff
--- a/src/app/webhooks/handler.py
+++ b/src/app/webhooks/handler.py
@@ -1,3 +1,8 @@
+from app.logging_config import get_logger
+
+
+def handle_event(event: dict) -> None:
+    """Log the verified event. Fast, inline, correct."""
+    get_logger().info("webhook_event", event_type=event.get("type", "unknown"))
```

- [ ] **Step 5: Verify fixture wiring (hermetic).** Confirm the eval harness discovers the new fixtures without a real key:

Run: `uv run pytest tests/ -k eval -v` (or the harness's fixture-discovery test). Expected: the new fixtures are collected; no scoring runs without a key. If the harness has a test asserting every fixture has the right shape, it should pass.

> Thresholds: leave `tests/eval/fixtures/thresholds.yaml` on defaults (`recall_min 0.67`, `fp_max 0.34`); the architecture agent already uses defaults. A real eval run (Plan 9) tunes if needed. Do NOT invent a threshold.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/agents/architecture.md tests/eval/fixtures/architecture
git commit -m "feat(review): architecture agent flags heavy inline work -> recommend workers battery"
```

---

### Task 13: Integrity + CLI integration (new / upskill / downskill)

**Files:**
- Test: `tests/test_integrity_workers.py` (add) or extend the existing battery-integrity test module

- [ ] **Step 1: `framework new --with workers` → integrity green.** Write a test that renders a project with the battery via the CLI path and asserts the manifest verifies (mirror the existing `--with webhooks` integrity test):

```python
def test_new_with_workers_integrity_is_green(tmp_path: Path):
    project = _framework_new(tmp_path, batteries=["workers"])   # reuse the helper webhooks integrity tests use
    from framework_cli.integrity.checker import check
    result = check(project, ci=True)
    assert result.ok, result
```

> This proves the LOCKED files that workers conditionally renders (`dev.yml`, `prometheus.yml`) are checksummed at their battery-active content and verify clean — workers is the first battery to exercise conditional LOCKED rendering.

- [ ] **Step 2: Run, confirm pass** (the manifest is written at `new` time over the rendered tree).

- [ ] **Step 3: `framework downskill workers` reverts LOCKED files + preserves the migration.** Write a test (mirror `test_downskill.py` integration style):

```python
def test_downskill_workers_reverts_and_preserves_migration(tmp_path: Path):
    project = _framework_new(tmp_path, batteries=["workers"], git_init=True)
    from framework_cli.downskill import remove_battery
    from framework_cli.source import read_batteries

    report = remove_battery(project, "workers")

    # owned files gone
    assert not (project / "src" / PKG / "tasks").exists()
    # migration preserved (a DB may be at 0003) + warned
    assert (project / "migrations" / "versions" / "0003_dead_letter.py").exists()
    assert any("migration" in w for w in report.warnings)
    # LOCKED shared files reverted to the no-workers render
    assert "celery-exporter" not in (project / "infra" / "compose" / "dev.yml").read_text()
    assert "celery-exporter" not in (project / "infra" / "observability" / "prometheus" / "prometheus.yml").read_text()
    # managed sections de-injected
    assert "APP_CELERY_BROKER_URL" not in (project / ".env.example").read_text()
    assert "worker:" not in (project / "Taskfile.yml").read_text()
    assert read_batteries(project) == []
    # integrity green after the regen
    from framework_cli.integrity.checker import check
    assert check(project, ci=True).ok
```

> This validates the 8a-2 ↔ 8c interaction: downskill's "shared changed file, builder-unmodified → overwrite with reduced render" path now covers **LOCKED** files (`dev.yml`, `prometheus.yml`) for the first time, the hybrid `_restore_section` covers `.env.example` **and** `Taskfile.yml`, and `workers_alerts.yml`/`workers.json`/the `tasks/` package are owned-file deletions. The `0003` migration is preserved.

- [ ] **Step 4: Run, confirm pass.** Fix any gaps (if downskill leaves a workers artifact, that's a real defect to resolve here). `ruff`/`mypy` clean.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test(workers): new integrity green + downskill reverts locked files & preserves migration"
```

---

### Task 14: Docker acceptance variants

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Add the with-workers acceptance test** (mirror `test_rendered_project_with_webhooks_battery_passes` at line ~119 — render `--with workers`, then run the gate). The generated unit+functional tests (Tasks 4–8) cover the battery; the coverage gate proves it:

```python
def test_rendered_project_with_workers_battery_passes(tmp_path: Path):
    dest = _render_project(tmp_path, batteries=["workers"])   # reuse the helper the webhooks variant uses
    # the generated suite runs Celery in eager mode (no live broker needed for coverage)
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 2: Add the webhooks+workers migration-chain + composition acceptance test.** This proves `alembic upgrade head` walks `0001 → 0002 → 0003` and the handler enqueues:

```python
def test_rendered_project_webhooks_and_workers_migration_chain(tmp_path: Path):
    dest = _render_project(tmp_path, batteries=["webhooks", "workers"])
    # the migration env + chain apply cleanly against a real Postgres in the generated suite
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    handler = (dest / "src" / PKG / "webhooks" / "handler.py").read_text()
    assert "process_async.delay" in handler
```

> The generated functional suite for the combined project includes the webhooks tests (which run migrations) and the workers tests; a clean `coverage.sh` run means `alembic upgrade head` applied `0001→0002→0003` with no `ModuleNotFoundError` (env.py imports both models). If the generated webhooks functional tests assume `handle_event` logs inline, they will now enqueue instead — **update the generated webhooks functional test** (`test_webhooks.py.jinja`) so its dedup assertion does not depend on the inline log when workers is present (gate that assertion `{% if "workers" not in batteries %}`), OR assert on the inbox row (provider-agnostic) which holds either way. Prefer asserting the inbox row.

- [ ] **Step 3: Run the acceptance suite** (Docker required):

Run: `rm -rf /tmp/pytest-of-$USER; uv run pytest tests/acceptance/test_rendered_project.py -k "workers" -v`
Expected: both new tests PASS (real Postgres via testcontainers; eager Celery).

- [ ] **Step 4: Commit**

```bash
git add tests/acceptance/test_rendered_project.py src/framework_cli/template
git commit -m "test(acceptance): with-workers green + webhooks+workers migration chain & composition"
```

---

## Final verification (controller, before finishing the branch)

Run the full gate and the end-to-end checks the final reviewer will repeat:

```bash
uv run ruff check .
uv run mypy src
uv lock --check
rm -rf /tmp/pytest-of-$USER
uv run pytest -q          # full suite incl. Docker acceptance — all green
uv build                  # wheel still builds; tasks payload ships as template data
```

Manual end-to-end spot check (no Docker needed):
- `framework new --with workers` in a tmp dir → `framework integrity --ci` green; `tasks/` package + `0003_dead_letter.py` present; `dev.yml` has `redis`/`worker`/`beat`/`celery-exporter`; `prometheus.yml` has the `celery` scrape job; `.env.example` + `Taskfile.yml` carry the `APP_CELERY_*` / `worker:` content **inside** the managed markers.
- `framework new` (no battery) → `dev.yml`/`prometheus.yml` byte-identical to pre-8c; no `tasks/`, no `0003`.
- `framework downskill workers` on the workers project → reverts the LOCKED files, de-injects both managed sections, preserves `0003`, integrity green.

---

## Self-Review (run against the spec)

**Spec coverage:**
- §1 standalone battery, `requires=()` → Task 1. ✓
- §2 tasks package (app/base/dead_letter/tasks/schedule) → Tasks 2,3,4,5,6. ✓
- §3 DB DLQ + templated migration ordering → Tasks 3,4 + acceptance chain Task 14. ✓
- §4 beat + heartbeat + healthchecks → Task 6 (heartbeat/liveness), Task 9 (container healthchecks), Task 8 (/health). ✓
- §5 observability contract: celery-exporter scrape target (Task 10), DLQ gauge on /metrics (Task 8), alert rules (Task 10), dashboard (Task 10), /health per-instance comment (Task 8). ✓
- §6 settings + .env.example injection + integrity reuse → Task 7 + Task 13. ✓
- §7 additive webhooks composition → Task 11. ✓
- §8 review heuristic + 1 eval fixture → Task 12. ✓
- §9 dev-compose services + Taskfile tasks → Task 9 + Task 7. ✓
- §10 testing tiers (unit/render/integrity/acceptance/eval) → distributed across tasks; Docker acceptance Task 14. ✓
- §11 follow-ups (8b-1/8e-1) → recorded in the meta-plan (controller already added rows); no task here. ✓

**Deviations from spec (intentional, noted):**
1. Migration revision ids use the repo's real bare convention (`"0003"`, `down_revision "0002"/"0001"`), not the `0002_webhook_events`/`0003_dead_letter` strings the spec table wrote — the spec's mechanic is unchanged; the actual webhooks migration uses bare `"0002"`.
2. `task worker`/`task beat` live **inside** the Taskfile managed section (the spec said "below FRAMEWORK:END") so `downskill` removes them via the hybrid section re-render — the below-marker placement would have leaked.
3. Acceptance uses Celery **eager mode** for deterministic in-process coverage rather than spinning a live worker against a real broker in the coverage run; the live worker+redis path is exercised by the dev compose (`task dev`) and can be validated by a dev-stack live test as a follow-up. This is sound test design (determinism) and still proves on_failure→DLQ, the gauge, /health, and the migration chain.

**Placeholder scan:** no TBD/TODO; every code step shows code; the one prose-only spot (Task 10 Step 4 Grafana JSON) points at the existing `slo.json` for the exact schema — acceptable because the dashboard JSON is large boilerplate and the panels/queries are specified.

**Type consistency:** `render_dlq_metrics(session)`, `count(session)`, `record_failure(session, *, ...)`, `list_recent(session, limit)`, `write_heartbeat(client, *, now)`, `is_alive(client, *, now, max_age)`, `register_schedule(app)`, `process_async.delay`, `heartbeat` — names are consistent across Tasks 4, 5, 6, 8, 11.

---

*End of plan. Next step: execution via superpowers:subagent-driven-development.*
