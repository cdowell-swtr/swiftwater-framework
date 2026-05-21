# Database Lifecycle (Plan 3c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generated projects ship a working relational data layer — PostgreSQL + SQLAlchemy + Alembic — that migrates and seeds itself on first `task dev`, tests itself against **real Postgres** (not a SQLite stand-in), and isolates its test data behind an ephemeral `postgres-test` service.

**Architecture:** Add a `db/` package to the template payload (declarative `Base`, an engine/session factory, an example `Item` model, a repository, an idempotent seed). Alembic config lives at the project root with a committed initial migration. The app container's `ENTRYPOINT` runs `alembic upgrade head` → seed → exec the server, so `task dev` is migrate-and-seed-on-first-run automatically. Compose gains `postgres` (dev/lite, persistent volume) and `postgres-test` (test, tmpfs — reset every run). The generated project's own DB tests run against a real Postgres started by **testcontainers** inside pytest; with no Docker they **fail** (deliberate forcing function — the real world is containerized). A Docker-gated framework acceptance test exercises the full stack end-to-end.

**Tech Stack:** SQLAlchemy 2.0 (sync, typed `Mapped[...]`), Alembic, psycopg 3 (`psycopg[binary]`), testcontainers-python, FastAPI dependency injection, Docker Compose, Taskfile, Copier (Jinja) template payload.

---

## Scope

This is the **relational paradigm only** (PostgreSQL + SQLAlchemy + Alembic), scaffolded **unconditionally** into every generated project — consistent with how 3a/3b added the runtime and observability stacks (always-on, not battery-gated). The multi-paradigm `--with database` wizard (Mongo, Redis, Neo4j, Qdrant, pgvector, Timescale) and copier-conditional gating are **Plan 8 / the database battery** — out of scope here. Spec references: §9 (Relational row of the paradigm table), §14 "Database Initialisation" + "Test Database Isolation", §15 `task db:migrate` / `task db:seed`, file-tree `migrations/` + `seeds/`.

## Two test layers (read this first — it shapes every task)

There are two distinct questions, and they have different Docker requirements:

- **Layer A — "Did the framework scaffold correctly?"** Template renders, files interpolate, paths resolve. Lives in **`tests/test_copier_runner.py`** (framework repo). **No Docker.** These run everywhere and are the red/green signal for most tasks below.
- **Layer B — "Does the generated thing actually work?"** Real Postgres, migrations apply, the app serves DB-backed data. The generated project's DB tests use **testcontainers** (a real `postgres:17` started inside pytest) and **hard-fail without Docker** — that failure is the forcing function that makes a builder install Docker. No SQLite fallback anywhere.

Consequences for the framework's own acceptance suite (`tests/acceptance/test_rendered_project.py`):
- The acceptance tests that **run the rendered project's test suite** (`test_rendered_project_passes_its_own_tests`, `test_rendered_project_coverage_gate_passes`) become **Docker-gated** — they need Docker because the rendered suite now does. Framework CI has Docker; a no-Docker box skips them (Layer A still covers scaffolding).
- `test_rendered_project_precommit_runs_clean` and `test_rendered_project_precommit_config_is_valid` stay **no-Docker** (they run ruff/mypy/gitleaks/config validation, not pytest), so the new `db/` code is still verified clean everywhere.

## File Structure

All paths are under the template payload `src/framework_cli/template/` unless they start with `tests/` (those are **framework** tests at the repo root). Brace paths like `src/{{package_name}}/` are Copier path templating — leave the braces.

**New template files (generated-project payload):**
- `src/{{package_name}}/db/__init__.py` — package marker
- `src/{{package_name}}/db/base.py` — `Base(DeclarativeBase)` (static `.py`, relative imports)
- `src/{{package_name}}/db/engine.py` — `build_engine`, `build_session_factory`, module `engine`/`SessionLocal`, `get_session` dependency (static `.py`)
- `src/{{package_name}}/db/models.py` — `Item` model (static `.py`)
- `src/{{package_name}}/db/repository.py` — `list_items`, `create_item` (static `.py`)
- `src/{{package_name}}/db/seed.py` — `seed(session, seeds_path)` idempotent (static `.py`)
- `src/{{package_name}}/routes/items.py` — `GET /items` (static `.py`, relative imports)
- `seeds/items.json` — seed data (static)
- `scripts/seed.py.jinja` — seed CLI (needs `{{ package_name }}`)
- `scripts/entrypoint.sh` — migrate → seed → exec server (static, executable)
- `alembic.ini` — Alembic config (static)
- `migrations/env.py.jinja` — Alembic env (needs `{{ package_name }}`)
- `migrations/script.py.mako` — Alembic revision template (static; mako, NOT rendered by Copier)
- `migrations/versions/0001_initial.py` — initial migration (static)
- `tests/conftest.py.jinja` — Postgres-container fixtures (`pg_url`, `engine`, `db_session`); fails clearly without Docker
- Generated tests (all `.jinja`): `tests/unit/test_db_engine.py.jinja`, `tests/unit/test_db_repository.py.jinja`, `tests/unit/test_db_seed.py.jinja`, `tests/unit/test_db_migrations.py.jinja`, `tests/functional/test_items_route.py.jinja`

**Modified template files:**
- `src/{{package_name}}/config/settings.py.jinja` — add `database_url`
- `src/{{package_name}}/main.py.jinja` — include `items` router
- `pyproject.toml.jinja` — runtime deps `sqlalchemy`/`alembic`/`psycopg[binary]`; dev dep `testcontainers[postgresql]`
- `infra/docker/Dockerfile.jinja` — `chmod +x` + `ENTRYPOINT`
- `infra/compose/dev.yml.jinja` — `postgres` service (dev/lite), app `depends_on` + `APP_DATABASE_URL`, top-level `pgdata` volume
- `infra/compose/test.yml.jinja` — `postgres-test` service + app DB env + `depends_on`
- `Taskfile.yml.jinja` — `db:migrate`, `db:seed`
- `.env.example` — `APP_DATABASE_URL`
- `SERVICES.md.jinja` — postgres row
- `README.md.jinja` — Database section + `/items` endpoint
- `tests/unit/test_settings.py.jinja` — `database_url` assertions (pure, no Docker)

**Modified framework tests (repo root):**
- `tests/test_copier_runner.py` — render assertions (Layer A)
- `tests/acceptance/test_rendered_project.py` — Docker-gate the rendered-suite/coverage tests; add a Docker-gated end-to-end `/items` test

---

## Conventions for every task (read once)

- **Environment:** `uv` and `task` live at `~/.local/bin` (ensure on `PATH`). `uv sync`/`uv run pytest` need the sandbox **disabled** (network for `uv sync`); `ruff`/`mypy` run in-sandbox. Git config writes fail — commit with inline identity: `git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" commit ...`. Add a `Co-Authored-By` trailer per the review-model policy.
- **Do NOT touch** `CLAUDE.md`, the meta-plan, or this plan doc. The controller updates state centrally at finish. If the commit hook blocks you because `CLAUDE.md` is unstaged, **report and stop** — do not edit `CLAUDE.md` yourself.
- **Primary signal per task = the Layer A render test** (`uv run pytest tests/test_copier_runner.py -q`) — fast, no Docker. The Layer B generated tests are written in the same task but only *executed* end-to-end where Docker exists (Task 13 / framework CI). Where you have Docker, you may additionally render a project and run its `uv run pytest` to confirm Layer B; where you don't, rely on the render assertions + lint/type checks.
- The generated project's gate is **ruff + mypy on `src/` only** (via pre-commit). The `db/` modules and `routes/items.py` must be ruff-clean and mypy-clean. `migrations/`, `scripts/`, `seeds/`, and `tests/` are outside `src/` — not mypy-checked — but `.py` files there are still ruff-linted by `pre-commit run --all-files`, so keep them clean (no unused imports).
- TDD: write the failing test, confirm red, implement the minimum, confirm green, commit.

---

### Task 1: Settings `database_url` + dependencies

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja:5-24`
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja:24`
- Modify: `src/framework_cli/template/tests/unit/test_settings.py.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_pyproject_database_deps(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    pyproject = (dest / "pyproject.toml").read_text()
    assert "sqlalchemy" in pyproject
    assert "alembic" in pyproject
    assert "psycopg" in pyproject
    assert "testcontainers" in pyproject  # dev dep for real-PG tests


def test_render_settings_has_database_url(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    settings = (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "database_url" in settings
    assert "postgresql+psycopg://" in settings
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_pyproject_database_deps tests/test_copier_runner.py::test_render_settings_has_database_url -q`
Expected: FAIL.

- [ ] **Step 3: Add the dependencies**

In `pyproject.toml.jinja`, append the three runtime deps to `dependencies` and add the test dep to `[dependency-groups] dev`:

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.32",
    "pydantic-settings>=2.6",
    "structlog>=24.4",
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-grpc>=1.27",
    "opentelemetry-instrumentation-fastapi>=0.48b0",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-cov>=6.0",
    "httpx>=0.28",
    "ruff>=0.8",
    "mypy>=1.13",
    "pre-commit>=4.0",
    "pyyaml>=6.0",
    "testcontainers[postgresql]>=4.8",
]
```

- [ ] **Step 4: Add the setting**

In `settings.py.jinja`, after the `otel_exporter_otlp_endpoint` line (line 24), add:

```python
    # Database connection (SQLAlchemy URL). The Compose stack injects the in-network
    # URL; host tooling/tests use localhost (testcontainers overrides it per session).
    database_url: str = "postgresql+psycopg://app:app@postgres:5432/app"
```

- [ ] **Step 5: Extend the generated settings test (pure — no Docker)**

Append to `tests/unit/test_settings.py.jinja`:

```python
def test_database_url_default():
    assert Settings().database_url.startswith("postgresql+psycopg://")


def test_database_url_env_override(monkeypatch):
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql+psycopg://x@y:5432/z")
    assert Settings().database_url == "postgresql+psycopg://x@y:5432/z"
```

- [ ] **Step 6: Run render tests to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_pyproject_database_deps tests/test_copier_runner.py::test_render_settings_has_database_url -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/pyproject.toml.jinja \
        src/framework_cli/template/src/'{{package_name}}'/config/settings.py.jinja \
        src/framework_cli/template/tests/unit/test_settings.py.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): add database_url setting + SQLAlchemy/Alembic/psycopg/testcontainers deps"
```

---

### Task 2: DB core + Postgres-container test fixtures

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/db/__init__.py`
- Create: `src/framework_cli/template/src/{{package_name}}/db/base.py`
- Create: `src/framework_cli/template/src/{{package_name}}/db/engine.py`
- Create: `src/framework_cli/template/tests/conftest.py.jinja`
- Create: `src/framework_cli/template/tests/unit/test_db_engine.py.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_includes_db_core(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    db = dest / "src" / "demo" / "db"
    assert (db / "base.py").is_file()
    engine = (db / "engine.py").read_text()
    assert "def get_session" in engine
    assert "build_engine" in engine


def test_render_conftest_uses_real_postgres(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    conftest = (dest / "tests" / "conftest.py").read_text()
    assert "PostgresContainer" in conftest
    assert "db_session" in conftest
    # forcing function: DB tests fail (not silently skip) without Docker
    assert "pytest.fail" in conftest
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_db_core tests/test_copier_runner.py::test_render_conftest_uses_real_postgres -q`
Expected: FAIL.

- [ ] **Step 3: Create the package marker**

`src/{{package_name}}/db/__init__.py`:

```python
```
(empty file)

- [ ] **Step 4: Create `base.py`**

`src/{{package_name}}/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
```

- [ ] **Step 5: Create `engine.py`**

`src/{{package_name}}/db/engine.py`:

```python
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config.settings import get_settings


def build_engine(url: str) -> Engine:
    """Create a connection-pooled Engine for the given SQLAlchemy URL."""
    return create_engine(url, pool_pre_ping=True, future=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine: Engine = build_engine(get_settings().database_url)
SessionLocal: sessionmaker[Session] = build_session_factory(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: a session per request, always closed."""
    with SessionLocal() as session:
        yield session
```

- [ ] **Step 6: Create the test fixtures `tests/conftest.py.jinja`**

`tests/conftest.py.jinja`:

```python
import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from {{ package_name }}.db.engine import build_engine


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """A real Postgres started for the test session. Fails (not skips) without Docker."""
    from testcontainers.postgres import PostgresContainer

    try:
        container = PostgresContainer("postgres:17", driver="psycopg")
        container.start()
    except Exception as exc:  # Docker unavailable, image pull failed, etc.
        pytest.fail(
            "Database tests need Docker (a Postgres test container). "
            f"Install/start Docker and retry. Underlying error: {exc}"
        )
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture(scope="session")
def engine(pg_url: str) -> Engine:
    """Engine bound to the test Postgres, with the schema applied via Alembic."""
    subprocess.run(
        ["alembic", "upgrade", "head"],
        env={**os.environ, "APP_DATABASE_URL": pg_url},
        check=True,
        capture_output=True,
        text=True,
    )
    return build_engine(pg_url)


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Per-test session wrapped in a transaction rolled back at teardown for isolation.

    `join_transaction_mode="create_savepoint"` keeps isolation even when the code under
    test calls `session.commit()` (the commit becomes a savepoint inside the outer txn).
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# Keep imports referenced for tools that flag unused (sys is used by some test helpers).
_ = sys
```

> Drop the trailing `_ = sys` / `import sys` if `sys` is genuinely unused — written here only to show the import block; remove unused imports to stay ruff-clean. (Final form: only `os`, `subprocess`, `Iterator`, `pytest`, `Engine`, `Session`, `build_engine` — all used.)

Final, ruff-clean import block to actually ship (replace the above import lines):

```python
import os
import subprocess
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from {{ package_name }}.db.engine import build_engine
```

…and delete the `_ = sys` line.

- [ ] **Step 7: Write the generated-project engine test (Layer B — real Postgres)**

`tests/unit/test_db_engine.py.jinja`:

```python
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_get_session_executes_against_postgres(db_session: Session):
    assert db_session.execute(text("SELECT 1")).scalar() == 1
```

- [ ] **Step 8: Run render tests to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_db_core tests/test_copier_runner.py::test_render_conftest_uses_real_postgres -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/framework_cli/template/src/'{{package_name}}'/db \
        src/framework_cli/template/tests/conftest.py.jinja \
        src/framework_cli/template/tests/unit/test_db_engine.py.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): add DB core (Base/engine/get_session) + testcontainers PG fixtures"
```

---

### Task 3: `Item` model + repository

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/db/models.py`
- Create: `src/framework_cli/template/src/{{package_name}}/db/repository.py`
- Create: `src/framework_cli/template/tests/unit/test_db_repository.py.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_includes_db_model_and_repository(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    models = (dest / "src" / "demo" / "db" / "models.py").read_text()
    assert "class Item" in models
    assert '__tablename__ = "items"' in models
    repo = (dest / "src" / "demo" / "db" / "repository.py").read_text()
    assert "def list_items" in repo
    assert "def create_item" in repo
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_db_model_and_repository -q`
Expected: FAIL.

- [ ] **Step 3: Create `models.py`**

`src/{{package_name}}/db/models.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Item(Base):
    """Example entity — replace with your domain models."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 4: Create `repository.py`**

`src/{{package_name}}/db/repository.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Item


def list_items(session: Session) -> list[Item]:
    return list(session.scalars(select(Item).order_by(Item.id)))


def create_item(session: Session, name: str) -> Item:
    item = Item(name=name)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
```

- [ ] **Step 5: Write the generated-project repository test (Layer B)**

`tests/unit/test_db_repository.py.jinja`:

```python
from sqlalchemy.orm import Session

from {{ package_name }}.db.repository import create_item, list_items


def test_create_and_list_items(db_session: Session):
    assert list_items(db_session) == []
    created = create_item(db_session, "alpha")
    assert created.id is not None
    assert created.created_at is not None  # server_default applied by Postgres
    assert [i.name for i in list_items(db_session)] == ["alpha"]
```

- [ ] **Step 6: Run render test to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_db_model_and_repository -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/src/'{{package_name}}'/db/models.py \
        src/framework_cli/template/src/'{{package_name}}'/db/repository.py \
        src/framework_cli/template/tests/unit/test_db_repository.py.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): add Item model and items repository"
```

---

### Task 4: Idempotent seed + seed data + seed CLI

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/db/seed.py`
- Create: `src/framework_cli/template/seeds/items.json`
- Create: `src/framework_cli/template/scripts/seed.py.jinja`
- Create: `src/framework_cli/template/tests/unit/test_db_seed.py.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_includes_seed(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    seed_mod = (dest / "src" / "demo" / "db" / "seed.py").read_text()
    assert "def seed" in seed_mod
    data = json.loads((dest / "seeds" / "items.json").read_text())
    assert isinstance(data, list) and data and "name" in data[0]
    cli = (dest / "scripts" / "seed.py").read_text()
    assert "from demo.db.seed import seed" in cli
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_seed -q`
Expected: FAIL.

- [ ] **Step 3: Create `seed.py`**

`src/{{package_name}}/db/seed.py`:

```python
import json
from pathlib import Path

from sqlalchemy.orm import Session

from .models import Item
from .repository import list_items


def seed(session: Session, seeds_path: Path) -> int:
    """Idempotently load items from a JSON file. Returns the number of rows inserted.

    A no-op (returns 0) if the table already has rows — safe to run on every startup.
    """
    if list_items(session):
        return 0
    rows = json.loads(Path(seeds_path).read_text())
    for row in rows:
        session.add(Item(name=row["name"]))
    session.commit()
    return len(rows)
```

- [ ] **Step 4: Create `seeds/items.json`**

`seeds/items.json`:

```json
[
  { "name": "alpha" },
  { "name": "beta" }
]
```

- [ ] **Step 5: Create the seed CLI**

`scripts/seed.py.jinja`:

```python
from pathlib import Path

from {{ package_name }}.db.engine import SessionLocal
from {{ package_name }}.db.seed import seed


def main() -> None:
    with SessionLocal() as session:
        count = seed(session, Path("seeds/items.json"))
        print(f"seeded {count} items")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Write the generated-project seed test (Layer B)**

`tests/unit/test_db_seed.py.jinja`:

```python
import json
from pathlib import Path

from sqlalchemy.orm import Session

from {{ package_name }}.db.repository import list_items
from {{ package_name }}.db.seed import seed


def test_seed_is_idempotent(tmp_path: Path, db_session: Session):
    seeds = tmp_path / "items.json"
    seeds.write_text(json.dumps([{"name": "one"}, {"name": "two"}]))
    assert seed(db_session, seeds) == 2
    assert seed(db_session, seeds) == 0  # already seeded → no-op
    assert len(list_items(db_session)) == 2
```

- [ ] **Step 7: Run render test to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_seed -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/src/'{{package_name}}'/db/seed.py \
        src/framework_cli/template/seeds/items.json \
        src/framework_cli/template/scripts/seed.py.jinja \
        src/framework_cli/template/tests/unit/test_db_seed.py.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): add idempotent seed, seed data, and seed CLI"
```

---

### Task 5: Alembic config + env + initial migration

**Files:**
- Create: `src/framework_cli/template/alembic.ini`
- Create: `src/framework_cli/template/migrations/env.py.jinja`
- Create: `src/framework_cli/template/migrations/script.py.mako`
- Create: `src/framework_cli/template/migrations/versions/0001_initial.py`
- Create: `src/framework_cli/template/tests/unit/test_db_migrations.py.jinja`
- Test: `tests/test_copier_runner.py`

> **Note on `script.py.mako`:** it is NOT a Jinja template — Copier only renders files ending in `.jinja` (`_templates_suffix: .jinja`), so the mako `${...}` syntax is copied verbatim. Do not rename it.
>
> The `conftest.engine` fixture (Task 2) already runs `alembic upgrade head` against the test Postgres to build the schema — so this migration is exercised by **every** Layer B test, and the dedicated test below just asserts the resulting table exists.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_includes_alembic(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ini = (dest / "alembic.ini").read_text()
    assert "script_location = migrations" in ini
    env = (dest / "migrations" / "env.py").read_text()
    assert "from demo.db.base import Base" in env
    assert "get_settings().database_url" in env
    assert (dest / "migrations" / "script.py.mako").is_file()
    initial = (dest / "migrations" / "versions" / "0001_initial.py").read_text()
    assert "create_table" in initial and '"items"' in initial
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_alembic -q`
Expected: FAIL.

- [ ] **Step 3: Create `alembic.ini`**

`alembic.ini`:

```ini
[alembic]
script_location = migrations
prepend_sys_path = src
```

- [ ] **Step 4: Create `migrations/env.py.jinja`**

`migrations/env.py.jinja`:

```python
from sqlalchemy import engine_from_config, pool

from alembic import context

from {{ package_name }}.config.settings import get_settings
from {{ package_name }}.db import models  # noqa: F401  (registers tables on Base.metadata)
from {{ package_name }}.db.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 5: Create `migrations/script.py.mako`**

`migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6: Create the initial migration**

`migrations/versions/0001_initial.py`:

```python
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-21

"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("items")
```

- [ ] **Step 7: Write the generated-project migration test (Layer B)**

`tests/unit/test_db_migrations.py.jinja`:

```python
from sqlalchemy import Engine, inspect


def test_migrations_create_items_table(engine: Engine):
    # The `engine` fixture applies migrations via `alembic upgrade head`; assert the
    # schema landed on real Postgres.
    assert "items" in inspect(engine).get_table_names()
```

- [ ] **Step 8: Run render test to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_alembic -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/framework_cli/template/alembic.ini \
        src/framework_cli/template/migrations \
        src/framework_cli/template/tests/unit/test_db_migrations.py.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): add Alembic config, env, and initial items migration"
```

---

### Task 6: `/items` route + wire into the app

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/routes/items.py`
- Modify: `src/framework_cli/template/src/{{package_name}}/main.py.jinja:8,19`
- Create: `src/framework_cli/template/tests/functional/test_items_route.py.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_wires_items_route(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    items = (dest / "src" / "demo" / "routes" / "items.py").read_text()
    assert '@router.get("/items")' in items
    main = (dest / "src" / "demo" / "main.py").read_text()
    assert "items" in main
    assert "include_router(items.router)" in main
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_wires_items_route -q`
Expected: FAIL.

- [ ] **Step 3: Create the route**

`src/{{package_name}}/routes/items.py` (static `.py`, relative imports, `Annotated` to avoid B008):

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db.engine import get_session
from ..db.repository import list_items

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/items")
def get_items(session: SessionDep) -> list[dict[str, object]]:
    """List seeded/created items — demonstrates the DB wiring end to end."""
    return [{"id": item.id, "name": item.name} for item in list_items(session)]
```

- [ ] **Step 4: Wire it into `main.py.jinja`**

Change the import (line 8) from:

```python
from {{ package_name }}.routes import health
```
to:
```python
from {{ package_name }}.routes import health, items
```

And after `app.include_router(health.router)` (line 19) add:

```python
    app.include_router(items.router)
```

- [ ] **Step 5: Write the generated-project functional test (Layer B — real Postgres via override)**

`tests/functional/test_items_route.py.jinja`:

```python
from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from {{ package_name }}.db.engine import get_session
from {{ package_name }}.db.repository import create_item
from {{ package_name }}.main import create_app


def test_items_endpoint_returns_rows(db_session: Session):
    create_item(db_session, "alpha")

    def override() -> Iterator[Session]:
        yield db_session

    app = create_app()
    app.dependency_overrides[get_session] = override
    client = TestClient(app)

    resp = client.get("/items")
    assert resp.status_code == 200
    assert [row["name"] for row in resp.json()] == ["alpha"]
```

- [ ] **Step 6: Run render test to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_wires_items_route -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/src/'{{package_name}}'/routes/items.py \
        src/framework_cli/template/src/'{{package_name}}'/main.py.jinja \
        src/framework_cli/template/tests/functional/test_items_route.py.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): add GET /items route backed by the database"
```

---

### Task 7: Container entrypoint — migrate → seed → serve

**Files:**
- Create: `src/framework_cli/template/scripts/entrypoint.sh`
- Modify: `src/framework_cli/template/infra/docker/Dockerfile.jinja:10-15`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_dockerfile_entrypoint(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    entry = (dest / "scripts" / "entrypoint.sh").read_text()
    assert "alembic upgrade head" in entry
    assert "scripts/seed.py" in entry
    assert 'exec "$@"' in entry
    dockerfile = (dest / "infra" / "docker" / "Dockerfile").read_text()
    assert "entrypoint.sh" in dockerfile
    assert "ENTRYPOINT" in dockerfile
    assert "uvicorn" in dockerfile and "CMD" in dockerfile
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_dockerfile_entrypoint -q`
Expected: FAIL.

- [ ] **Step 3: Create the entrypoint**

`scripts/entrypoint.sh`:

```sh
#!/bin/sh
set -e

# On container start: apply pending migrations and load seed data (both idempotent),
# then hand off to the server command (uvicorn, passed as CMD / compose `command`).
alembic upgrade head
python scripts/seed.py
exec "$@"
```

Make it executable in the repo: `chmod +x src/framework_cli/template/scripts/entrypoint.sh` (Copier preserves the mode; the Dockerfile also `chmod`s it as a belt-and-braces step).

- [ ] **Step 4: Wire it into the Dockerfile**

Replace the runtime stage (lines 10-15) of `infra/docker/Dockerfile.jinja` with:

```dockerfile
FROM python:3.12-slim-bookworm AS runtime
ENV TZ=UTC PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /app /app
RUN chmod +x /app/scripts/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "{{ package_name }}.main:app"]
```

- [ ] **Step 5: Run render test to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_dockerfile_entrypoint -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/scripts/entrypoint.sh \
        src/framework_cli/template/infra/docker/Dockerfile.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): migrate+seed on container start via entrypoint"
```

---

### Task 8: Compose — `postgres` for dev/lite + app wiring

**Files:**
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_postgres_in_dev_and_lite(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    pg = dev["services"]["postgres"]
    assert pg["profiles"] == ["dev", "lite"]   # present in dev AND lite, not test
    assert "pg_isready" in " ".join(pg["healthcheck"]["test"])
    app = dev["services"]["app"]
    assert app["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "postgres:5432" in app["environment"]["APP_DATABASE_URL"]
    assert "pgdata" in dev["volumes"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_postgres_in_dev_and_lite -q`
Expected: FAIL.

- [ ] **Step 3: Add `postgres` and wire the app**

In `infra/compose/dev.yml.jinja`, extend the `app` service `environment` and add `depends_on`:

```yaml
  app:
    profiles: ["dev", "lite"]
    command: ["uvicorn", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--reload", "{{ package_name }}.main:app"]
    ports:
      - "8000:8000"
    volumes:
      - ../../src:/app/src
    environment:
      WATCHFILES_FORCE_POLLING: "true"  # reliable reload on Windows/WSL bind mounts
      APP_OTEL_ENABLED: "true"
      APP_OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
      APP_DATABASE_URL: "postgresql+psycopg://app:app@postgres:5432/app"
    depends_on:
      postgres:
        condition: service_healthy
```

Add the `postgres` service:

```yaml
  postgres:
    image: postgres:17
    profiles: ["dev", "lite"]
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 5s
    ports:
      - "5432:5432"
    volumes:
      - "pgdata:/var/lib/postgresql/data"
```

Add a top-level `volumes:` block at the end of the file (Compose merges top-level volumes across `-f` files):

```yaml
volumes:
  pgdata: {}
```

- [ ] **Step 4: Run render test to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_postgres_in_dev_and_lite -q`
Expected: PASS.

- [ ] **Step 5: Confirm existing compose tests still pass**

Run: `uv run pytest tests/test_copier_runner.py -k compose -q`
Expected: PASS (existing `test_render_compose_structure` + observability tests unaffected).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/infra/compose/dev.yml.jinja tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): add postgres to dev/lite compose with app dependency"
```

---

### Task 9: Compose — ephemeral `postgres-test` for the test profile

**Files:**
- Modify: `src/framework_cli/template/infra/compose/test.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_postgres_test_profile(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    test = yaml.safe_load((dest / "infra" / "compose" / "test.yml").read_text())
    pg = test["services"]["postgres-test"]
    assert pg["profiles"] == ["test"]
    assert "tmpfs" in pg  # ephemeral: reset between runs
    app = test["services"]["app"]
    assert "postgres-test:5432" in app["environment"]["APP_DATABASE_URL"]
    assert app["depends_on"]["postgres-test"]["condition"] == "service_healthy"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_postgres_test_profile -q`
Expected: FAIL.

- [ ] **Step 3: Rewrite `test.yml.jinja`**

`infra/compose/test.yml.jinja`:

```yaml
# test profile: app with test config + an ephemeral Postgres (reset every run via
# tmpfs). Seed for the E2E stack (Plan 5).
services:
  app:
    profiles: ["test"]
    environment:
      APP_ENVIRONMENT: test
      APP_DATABASE_URL: "postgresql+psycopg://app:app@postgres-test:5432/app"
    depends_on:
      postgres-test:
        condition: service_healthy

  postgres-test:
    image: postgres:17
    profiles: ["test"]
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 5s
      timeout: 3s
      retries: 10
    tmpfs:
      - /var/lib/postgresql/data
```

- [ ] **Step 4: Run render test to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_postgres_test_profile -q`
Expected: PASS. Also re-run `uv run pytest tests/test_copier_runner.py -k compose -q` — `test_render_compose_structure` still asserts `test.yml` app `APP_ENVIRONMENT == "test"` + profile `test`, both still true.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/infra/compose/test.yml.jinja tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): add ephemeral postgres-test to the test profile"
```

---

### Task 10: Taskfile — `db:migrate` and `db:seed`

**Files:**
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_db_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "db:migrate:" in taskfile
    assert "db:seed:" in taskfile
    assert "alembic upgrade head" in taskfile
    assert "scripts/seed.py" in taskfile
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_db_tasks -q`
Expected: FAIL.

- [ ] **Step 3: Add the tasks**

Append to `Taskfile.yml.jinja` (after the `observability:gen` task):

```yaml
  db:migrate:
    desc: Apply pending Alembic migrations (uses APP_DATABASE_URL; default localhost:5432).
    cmds:
      - uv run alembic upgrade head

  db:seed:
    desc: Load seed data (idempotent — skips if data already exists).
    cmds:
      - uv run python scripts/seed.py
```

- [ ] **Step 4: Run render test to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_db_tasks -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "feat(3c): add db:migrate and db:seed tasks"
```

---

### Task 11: Docs — `.env.example`, `SERVICES.md`, `README`

**Files:**
- Modify: `src/framework_cli/template/.env.example`
- Modify: `src/framework_cli/template/SERVICES.md.jinja`
- Modify: `src/framework_cli/template/README.md.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_database_docs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    env = (dest / ".env.example").read_text()
    assert "APP_DATABASE_URL=" in env
    services = (dest / "SERVICES.md").read_text()
    assert "postgres:5432" in services
    readme = (dest / "README.md").read_text()
    assert "task db:migrate" in readme
    assert "PostgreSQL" in readme
    assert "/items" in readme
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_database_docs -q`
Expected: FAIL.

- [ ] **Step 3: Add the DB var to `.env.example`**

Append to `.env.example`:

```bash
# Database. Host-side tooling (alembic, tests) uses localhost; the Compose stack
# injects the in-network URL (postgres / postgres-test).
APP_DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app
```

- [ ] **Step 4: Add the postgres row to `SERVICES.md.jinja`**

Add this row to the services table (after the `app` row is fine):

```markdown
| postgres | `postgres:5432` | `localhost:5432` | PostgreSQL (dev/lite); the `test` profile uses an ephemeral `postgres-test` |
```

- [ ] **Step 5: Add a Database section + `/items` endpoint to `README.md.jinja`**

Insert a `## Database` section before `## Endpoints`:

```markdown
## Database

PostgreSQL + SQLAlchemy + Alembic. The `dev`/`lite`/`test` stacks bring up Postgres
automatically; on first `task dev` the app container runs pending migrations and loads
seed data (`seeds/items.json`) before serving — idempotently, so later runs skip
seeding. `task dev:reset` drops the volume and rebuilds from scratch.

- `task db:migrate` — apply pending migrations (`alembic upgrade head`)
- `task db:seed` — load seed data
- Schema changes: edit the models, then
  `uv run alembic revision --autogenerate -m "..."`. Never edit an applied migration —
  add a new one.

Tests run against a **real Postgres** (started automatically via testcontainers), so
**Docker is required to run the test suite**. The `test` Compose profile provides a
separate, ephemeral Postgres (`postgres-test`, reset every run) for the full E2E stack.
```

And add to the `## Endpoints` list:

```markdown
- `GET /items` — example DB-backed listing (seeded data)
```

- [ ] **Step 6: Run render test to verify green**

Run: `uv run pytest tests/test_copier_runner.py::test_render_database_docs -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/.env.example \
        src/framework_cli/template/SERVICES.md.jinja \
        src/framework_cli/template/README.md.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "docs(3c): document the database layer in env/services/readme"
```

---

### Task 12: Framework acceptance — Docker-gate the rendered-suite tests + add live `/items` test

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`

> The rendered project's test suite now needs Docker (testcontainers). So the framework acceptance tests that *run that suite* must require Docker too. The lint/type acceptance tests stay no-Docker.

- [ ] **Step 1: Move `_docker_available()` above the first test**

`_docker_available()` is currently defined ~line 135, after the tests that need it in their decorators. Decorators evaluate at collection time, so move the helper to just below the imports/`DATA` block (before `test_rendered_project_passes_its_own_tests`). Its body is unchanged:

```python
def _docker_available() -> bool:
    if shutil.which("uv") is None or shutil.which("docker") is None:
        return False
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
    return result.returncode == 0
```

(Remove the now-duplicate definition further down.)

- [ ] **Step 2: Docker-gate the two suite-running tests**

Change the decorator on **`test_rendered_project_passes_its_own_tests`** and **`test_rendered_project_coverage_gate_passes`** from:

```python
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
```
to:
```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
```

Leave `test_rendered_project_precommit_config_is_valid` and `test_rendered_project_precommit_runs_clean` **unchanged** (no Docker — they run config validation + ruff/mypy/gitleaks, not pytest).

- [ ] **Step 3: Add the Docker-gated end-to-end `/items` test**

Append to `tests/acceptance/test_rendered_project.py`:

```python
@pytest.mark.skipif(not _docker_available(), reason="uv and docker are required for the live-stack test")
def test_rendered_project_dev_stack_serves_seeded_items(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    # `lite` profile = app + postgres only (no Traefik/observability) — app on 8000.
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        deadline = time.time() + 120
        items = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:8000/items", timeout=3) as resp:
                    if resp.status == 200:
                        payload = json.loads(resp.read())
                        if payload:
                            items = payload
                            break
            except OSError:
                pass
            time.sleep(3)
        assert items, "no seeded items served by /items within 120s"
        assert {row["name"] for row in items} >= {"alpha", "beta"}
    finally:
        subprocess.run(down, cwd=dest)
```

- [ ] **Step 4: Verify collection + gating without Docker**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -q`
Expected (no-Docker box): the suite-running tests + the new live test report `skipped`; the precommit tests run. No collection errors (confirms `_docker_available` is defined before use).

- [ ] **Step 5: Commit**

```bash
git add tests/acceptance/test_rendered_project.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" \
    commit -m "test(3c): Docker-gate rendered-suite acceptance tests; add live seeded /items test"
```

---

### Task 13: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Framework Layer-A gate (no Docker)**

Run:
```bash
uv run ruff check .
uv run mypy src
uv run pytest tests/test_copier_runner.py -q
```
Expected: ruff clean, mypy clean, all render tests PASS (including the ~10 new ones).

- [ ] **Step 2: Lint/type cleanliness of generated code (no Docker)**

Run (sandbox disabled — `uv sync` needs network):
```bash
uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_precommit_runs_clean -q
```
Expected: PASS. Guards that ruff/mypy/gitleaks pass on the new files — watch: ruff on `migrations/versions/0001_initial.py`, rendered `scripts/seed.py`, `tests/conftest.py`; mypy on `db/` + `routes/items.py`; gitleaks on `app:app@` URLs (low-entropy, should not trip — confirm).

- [ ] **Step 3: Layer-B end-to-end (REQUIRES Docker)**

If Docker is available in the execution environment, run (sandbox disabled):
```bash
uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_passes_its_own_tests \
              tests/acceptance/test_rendered_project.py::test_rendered_project_coverage_gate_passes \
              tests/acceptance/test_rendered_project.py::test_rendered_project_dev_stack_serves_seeded_items -q
```
Expected (with Docker): PASS — the rendered suite spins up Postgres via testcontainers, migrations apply, repo/seed/route/migration tests pass, coverage ≥ 70%, and the live stack serves the seeded `/items`.

If Docker is **not** available: these report `skipped`. That is acceptable for this slice's local verification — note it explicitly in the completion report and ensure they run in the framework's CI (which has Docker) before the work is considered fully validated. **Do not claim Layer B passed if it only skipped.**

- [ ] **Step 4: If anything fails, fix and re-run.** Report results with actual command output (per superpowers:verification-before-completion). State plainly which layers were executed vs skipped.

---

## Self-Review

**1. Spec coverage:**
- §9 Relational paradigm (PostgreSQL + SQLAlchemy + Alembic) → Tasks 1–5. ✅
- §14 Database Initialisation ("first run: wait for DB health, run migrations, load seed; subsequent runs skip; `dev:reset` rebuilds") → entrypoint (Task 7) + `depends_on: service_healthy` (Task 8) + idempotent seed (Task 4); `dev:reset` already does `down -v`. ✅
- §14 Test Database Isolation ("separate test DB in the test profile; reset between runs") → `postgres-test` + tmpfs (Task 9); the project's own tests use a real testcontainers Postgres with per-test transactional rollback isolation (Task 2 `db_session`). ✅
- §15 `task db:migrate` / `task db:seed` → Task 10. ✅
- File-tree `migrations/` + `seeds/` → Tasks 4–5. ✅
- "Read all config through settings; never hardcode" → `database_url` in settings (Task 1); compose injects via env. ✅

**2. Placeholder scan:** No TBD/TODO/"add error handling"/"similar to Task N". Every code step has complete content. (The Task 2 conftest shows the final ruff-clean import block explicitly.) ✅

**3. Type consistency:** `build_engine(url)`/`build_session_factory(engine)`/`get_session()` (Task 2) used consistently in `engine.py`, the route override (Task 6), and `SessionLocal` in the seed CLI (Task 4). `Item`/`list_items`/`create_item`/`seed(session, seeds_path)` signatures match across model (Task 3), repo (Task 3), seed (Task 4), route (Task 6), tests. Fixtures `pg_url`/`engine`/`db_session` (Task 2) are the names consumed by every Layer-B test (Tasks 2–6). The migration table `items` matches `Item.__tablename__` and columns. `APP_DATABASE_URL` is the single env override everywhere (settings, compose, conftest, `.env.example`). ✅

**Out-of-scope (deliberately):** multi-paradigm wizard, Redis, copier `--with database` gating, a DB readiness probe in `/health` (kept `slo.py` untouched to avoid coupling; `/items` is the end-to-end proof). These belong to Plan 8.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-21-database-lifecycle.md`.

**Execution: Subagent-Driven** (chosen). Per the established review-model policy: **Sonnet** implementer + first/spec check, **Opus** for the subjective code-quality review and the final review, run as separate dispatches. Implementers must not touch `CLAUDE.md`/meta-plan/this plan (controller updates state centrally at merge).
