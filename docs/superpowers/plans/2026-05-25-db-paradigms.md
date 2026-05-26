# Database Paradigm Batteries — Slice 1 (`pgvector` + `mongodb`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `pgvector` (postgres-extension) and `mongodb` (separate-service) database-paradigm batteries, and build the reusable N>2 migration-ordering helper they (and future paradigms) depend on.

**Architecture:** A framework-side `migration_down_revisions(batteries)` helper computes each migration battery's `down_revision` as the nearest present predecessor in a canonical order (fixed numeric revision ids), injected into the Copier context by both `render_project` and `upskill_project`. `pgvector` enables the `vector` extension on the always-on postgres + adds an `embeddings` table/repo (no new service). `mongodb` adds a `mongo` container + `pymongo` client + documents demo + full §5 observability (exporter scrape target, alerts, dashboard, `/health` check).

**Tech Stack:** Python 3.12, SQLAlchemy + alembic + `pgvector` (SQLAlchemy `Vector` type), `pymongo` (sync), Copier/Jinja, testcontainers (Postgres + Mongo), pytest.

**Spec:** `docs/superpowers/specs/2026-05-25-db-paradigms-design.md`

---

## Conventions you MUST follow

- **`src/framework_cli/template/` is template payload.** Files with `{{ }}`/`{% %}` in content are `.jinja`; plain relative-import files are `.py`. The framework's mypy/ruff exclude the template; it's validated by render tests + Docker acceptance.
- **THE JINJA-BRACE PITFALL:** in a `.jinja` file, `{{`/`{%`/`{#` are Jinja. Prometheus single-brace label selectors (`{outcome="x"}`) are safe; f-strings with doubled braces are NOT. In `.jinja` test files assert with plain literals / concatenation.
- **Whitespace control:** gated `{%- if %}` / `{%- endif %}` must keep the no-battery render byte-identical + ruff-format-clean. `dev.yml` and `prometheus.yml` are **LOCKED_TRACKED** — a gated edit must be byte-identical without the battery (the workers precedent; integrity stays green via the battery-aware manifest). `.env.example`/`Taskfile.yml` are **HYBRID_TRACKED** (managed `FRAMEWORK:BEGIN/END` sections). `conftest.py`/`settings.py`/`health.py`/`pyproject.toml` are non-tracked.
- **Tooling — FROZEN env** (the lockfile pins ruff 0.15.13): `uv run --frozen pytest -q && uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen mypy src`.
- **Commit-gate hook:** `git commit` is blocked unless `CLAUDE.md` is staged with its `- **Last updated:** …` line edited. Run `git add … CLAUDE.md` and `git commit` as **separate** Bash calls (a combined `add && commit` trips the hook).
- **Docker IS available** here — the acceptance tier runs (don't expect skips).

## File Structure

**Framework source:**
- Create `src/framework_cli/migrations.py` — the migration-ordering helper.
- Modify `src/framework_cli/copier_runner.py` — inject migration context in `render_project`.
- Modify `src/framework_cli/upskill.py` — inject the same context in `upskill_project`.
- Modify `src/framework_cli/batteries.py` — register `pgvector` + `mongodb`.
- Tests under `tests/` (`test_migrations.py`, `test_copier_runner.py`, `test_downskill.py`, `test_batteries.py`, `tests/acceptance/test_rendered_project.py`).

**Template payload:**
- `migrations/versions/{{ '0004_embeddings.py' if 'pgvector' in batteries else '' }}.jinja` (new); modify `…0003_dead_letter.py….jinja` (refactor `down_revision`); modify `migrations/env.py.jinja`.
- `src/{{package_name}}/{% if "pgvector" in batteries %}vectors{% endif %}/{__init__,models,repository}.py` (new).
- `src/{{package_name}}/{% if "mongodb" in batteries %}mongo{% endif %}/{__init__,client,repository}.py` (new).
- Modify `pyproject.toml.jinja`, `config/settings.py.jinja`, `routes/health.py.jinja`, `tests/conftest.py.jinja`, `infra/compose/dev.yml.jinja`, `infra/observability/prometheus/prometheus.yml.jinja`, `.env.example.jinja`, `Taskfile.yml.jinja`.
- `infra/observability/prometheus/alerts/{{ 'mongodb_alerts.yml' if 'mongodb' in batteries else '' }}.jinja` (new); `infra/observability/grafana/dashboards/{{ 'mongodb.json' if 'mongodb' in batteries else '' }}.jinja` (new).
- `tests/functional/{{ 'test_mongo.py' if 'mongodb' in batteries else '' }}.jinja`, `tests/functional/{{ 'test_vectors.py' if 'pgvector' in batteries else '' }}.jinja` (new).

> **[verify]** markers flag third-party specifics to confirm during the red/green loop: the `pgvector.sqlalchemy.Vector` import + the declarative `Base` name in `db/models.py`; the `pgvector/pgvector:pg17` testcontainers image; the `percona/mongodb_exporter` image tag + its metric names for the alert.

---

## Task 1: Migration-ordering helper + context injection + workers refactor

**Files:**
- Create: `src/framework_cli/migrations.py`
- Modify: `src/framework_cli/copier_runner.py:13-22`
- Modify: `src/framework_cli/upskill.py:56-63`
- Modify: `src/framework_cli/template/migrations/versions/{{ '0003_dead_letter.py' if 'workers' in batteries else '' }}.jinja:4,13`
- Test: `tests/test_migrations.py`, `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_migrations.py`:
```python
from framework_cli.migrations import migration_down_revisions as mdr


def test_empty():
    assert mdr([]) == {}


def test_single_migration_battery_chains_to_baseline():
    assert mdr(["pgvector"]) == {"pgvector": "0001"}
    assert mdr(["workers"]) == {"workers": "0001"}


def test_webhooks_then_pgvector_skips_absent_workers():
    assert mdr(["webhooks", "pgvector"]) == {"webhooks": "0001", "pgvector": "0002"}


def test_full_chain_in_canonical_order():
    got = mdr(["pgvector", "workers", "webhooks"])  # input order irrelevant
    assert got == {"webhooks": "0001", "workers": "0002", "pgvector": "0003"}


def test_non_migration_batteries_ignored():
    assert mdr(["mongodb", "graphql", "webhooks"]) == {"webhooks": "0001"}
```

- [ ] **Step 2: Run to verify red**

Run: `uv run --frozen pytest tests/test_migrations.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement the helper**

Create `src/framework_cli/migrations.py`:
```python
"""Deterministic ordering of battery-contributed alembic migrations.

Each migration-adding battery has a FIXED numeric revision id (by canonical position) and a
`down_revision` computed as the nearest PRESENT predecessor in the canonical order (else the
baseline 0001). Revision ids are opaque alembic labels, so "gaps" (0001 -> 0003 when webhooks
is absent) are harmless and no renaming is needed.
"""

from __future__ import annotations

from collections.abc import Sequence

# Canonical order of migration-adding batteries (others add no alembic migration).
MIGRATION_ORDER: tuple[str, ...] = ("webhooks", "workers", "pgvector")
# Fixed revision id per battery (baseline is 0001).
REVISIONS: dict[str, str] = {"webhooks": "0002", "workers": "0003", "pgvector": "0004"}


def migration_down_revisions(batteries: Sequence[str]) -> dict[str, str]:
    """Map each present migration-adding battery to its down_revision (nearest present
    predecessor in canonical order, else '0001')."""
    present = [b for b in MIGRATION_ORDER if b in batteries]
    out: dict[str, str] = {}
    prev = "0001"
    for b in present:
        out[b] = prev
        prev = REVISIONS[b]
    return out


def migration_context(batteries: Sequence[str]) -> dict[str, str]:
    """Copier context vars `down_revision_<battery>` for each present migration battery."""
    return {f"down_revision_{b}": rev for b, rev in migration_down_revisions(batteries).items()}
```

- [ ] **Step 4: Inject into render + upskill**

In `src/framework_cli/copier_runner.py`, augment `data` before `run_copy`:
```python
def render_project(dest: Path, data: Mapping[str, object]) -> None:
    """Render the bundled template into `dest` using the provided answers."""
    from framework_cli.migrations import migration_context

    merged = dict(data)
    batteries = merged.get("batteries", []) or []
    merged.update(migration_context(batteries if isinstance(batteries, list) else []))
    run_copy(
        str(template_path()),
        str(dest),
        data=merged,
        defaults=True,
        overwrite=True,
        quiet=True,
    )
```

In `src/framework_cli/upskill.py`, inject the same into the `run_update` data:
```python
    from framework_cli.migrations import migration_context

    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref=vcs_ref,
        data={"batteries": effective, **migration_context(effective)},
    )
```

- [ ] **Step 5: Refactor the workers migration to the injected value**

In `…0003_dead_letter.py….jinja`, replace BOTH occurrences of `{{ '0002' if 'webhooks' in batteries else '0001' }}` (the `Revises:` docstring line 4 and `down_revision` line 13) with `{{ down_revision_workers }}`.

- [ ] **Step 6: Add a render test for the refactor**

Add to `tests/test_copier_runner.py`:
```python
def test_render_workers_migration_down_revision(tmp_path: Path):
    d1 = tmp_path / "w"
    render_project(d1, {**DATA, "batteries": ["workers"]})
    mig = next((d1 / "migrations" / "versions").glob("0003_*.py")).read_text()
    assert 'down_revision = "0001"' in mig

    d2 = tmp_path / "wh"
    render_project(d2, {**DATA, "batteries": ["webhooks", "workers"]})
    mig2 = next((d2 / "migrations" / "versions").glob("0003_*.py")).read_text()
    assert 'down_revision = "0002"' in mig2
```

- [ ] **Step 7: Verify green + full gate + commit**

Run: `uv run --frozen pytest tests/test_migrations.py tests/test_copier_runner.py -q` → PASS, then the full gate. Commit (hook steps):
Files: `src/framework_cli/migrations.py src/framework_cli/copier_runner.py src/framework_cli/upskill.py src/framework_cli/template/migrations tests/test_migrations.py tests/test_copier_runner.py CLAUDE.md`
Message: `feat(migrations): canonical-order down_revision helper + inject into render/upskill`

---

## Task 2: `pgvector` battery (extension, migration, model, repo, conftest image)

**Files:**
- Modify: `src/framework_cli/batteries.py`
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Create: `…/migrations/versions/{{ '0004_embeddings.py' if 'pgvector' in batteries else '' }}.jinja`
- Create: `…/src/{{package_name}}/{% if "pgvector" in batteries %}vectors{% endif %}/__init__.py`, `models.py`, `repository.py`
- Modify: `…/migrations/env.py.jinja`
- Modify: `…/tests/conftest.py.jinja`
- Create: `…/tests/functional/{{ 'test_vectors.py' if 'pgvector' in batteries else '' }}.jinja`
- Test: `tests/test_batteries.py`, `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_batteries.py`:
```python
def test_pgvector_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "pgvector" in battery_names()
    assert get_battery("pgvector").requires == ()
    assert resolve(["pgvector"]) == ["pgvector"]
```
Add to `tests/test_copier_runner.py`:
```python
def test_render_with_pgvector_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})
    pkg = dest / "src" / "demo"
    assert (pkg / "vectors" / "models.py").is_file()
    assert (pkg / "vectors" / "repository.py").is_file()
    mig = next((dest / "migrations" / "versions").glob("0004_*.py")).read_text()
    assert "CREATE EXTENSION" in mig and "vector" in mig
    assert 'down_revision = "0001"' in mig  # pgvector alone chains to baseline
    assert "pgvector" in (dest / "pyproject.toml").read_text()
    assert "pgvector/pgvector" in (dest / "tests" / "conftest.py").read_text()
    env = (dest / "migrations" / "env.py").read_text()
    assert "vectors" in env  # gated model import


def test_render_without_pgvector_clean(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "src" / "demo" / "vectors").exists()
    assert "pgvector" not in (dest / "pyproject.toml").read_text()
    assert "pgvector/pgvector" not in (dest / "tests" / "conftest.py").read_text()


def test_render_pgvector_battery_is_ruff_format_clean(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})
    _assert_ruff_format_clean(dest)
```

- [ ] **Step 2: Run to verify red**

Run: `uv run --frozen pytest tests/test_batteries.py tests/test_copier_runner.py -q -k pgvector` → FAIL.

- [ ] **Step 3: Register the battery + dep**

In `batteries.py` `_BATTERIES`, add:
```python
    "pgvector": BatterySpec(
        "pgvector",
        "PostgreSQL pgvector extension + an embeddings table for vector similarity search",
    ),
```
In `pyproject.toml.jinja`, add the gated dep alongside the others (after `pybreaker`, the celery-gating style):
```jinja
{% if "pgvector" in batteries %}    "pgvector>=0.3",
{% endif %}
```

- [ ] **Step 4: Create the model + repository**

`…/vectors/__init__.py`: empty. `…/vectors/models.py` (**[verify]** the `Vector` import + the `Base` symbol/location in `db/models.py`):
```python
from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..db.models import Base

_DIM = 1536


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    embedding: Mapped[list[float]] = mapped_column(Vector(_DIM))
```
`…/vectors/repository.py`:
```python
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Embedding


def add_embedding(session: Session, item_id: int, embedding: Sequence[float]) -> Embedding:
    row = Embedding(item_id=item_id, embedding=list(embedding))
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def nearest(session: Session, query: Sequence[float], k: int = 5) -> list[Embedding]:
    """The k nearest embeddings to `query` by cosine distance."""
    stmt = select(Embedding).order_by(Embedding.embedding.cosine_distance(list(query))).limit(k)
    return list(session.scalars(stmt))
```

- [ ] **Step 5: Create the migration**

`…/migrations/versions/{{ '0004_embeddings.py' if 'pgvector' in batteries else '' }}.jinja`:
```python
"""pgvector embeddings

Revision ID: 0004
Revises: {{ down_revision_pgvector }}

"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0004"
down_revision = "{{ down_revision_pgvector }}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
    )


def downgrade() -> None:
    # Drop the table; leave the `vector` extension (dropping a shared extension is destructive).
    op.drop_table("embeddings")
```

- [ ] **Step 6: Gate the model import in env.py**

In `migrations/env.py.jinja`, add to the conditional-imports block (next to the webhooks/workers imports):
```jinja
{% if "pgvector" in batteries %}from {{ package_name }}.vectors import models as _vector_models  # noqa: F401
{% endif %}
```

- [ ] **Step 7: Make the test Postgres pgvector-capable**

In `tests/conftest.py.jinja`, gate the testcontainers image so the `vector` extension is available when pgvector is present:
```jinja
        container = PostgresContainer("{% if "pgvector" in batteries %}pgvector/pgvector:pg17{% else %}postgres:17{% endif %}", driver="psycopg")
```
(Keep the line within ruff's length limit; if it over-runs, the format guard will catch it — split with the existing style.)

- [ ] **Step 8: Generated functional test**

`…/tests/functional/{{ 'test_vectors.py' if 'pgvector' in batteries else '' }}.jinja` (uses the `db_session` fixture; real pgvector Postgres):
```python
from {{ package_name }}.db.repository import create_item
from {{ package_name }}.vectors.repository import add_embedding, nearest


def test_nearest_returns_by_similarity(db_session):
    a = create_item(db_session, "a")
    b = create_item(db_session, "b")
    add_embedding(db_session, a.id, [1.0] + [0.0] * 1535)
    add_embedding(db_session, b.id, [0.0, 1.0] + [0.0] * 1534)
    hits = nearest(db_session, [1.0] + [0.0] * 1535, k=1)
    assert hits and hits[0].item_id == a.id
```

- [ ] **Step 9: Verify green + gate + commit**

Run the render tests + format guard (`-k pgvector`) → PASS; full gate. Commit (hook steps).
Message: `feat(pgvector): vector extension + embeddings table/repo battery`

---

## Task 3: `pgvector` Docker acceptance

**Files:** Modify `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Add the acceptance tests** (mirror `test_rendered_project_with_websockets_battery_passes`):
```python
@pytest.mark.skipif(not _docker_available(), reason="uv + docker required: real Postgres")
def test_rendered_project_with_pgvector_battery_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})
    assert (dest / "src" / "demo" / "vectors" / "repository.py").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cov = result.stdout + result.stderr
    line = next((ln for ln in cov.splitlines() if "vectors/repository.py" in ln), "")
    assert "100%" in line, f"vectors repo not fully exercised: {line!r}\n{cov}"


@pytest.mark.skipif(not _docker_available(), reason="uv + docker required: real Postgres")
def test_rendered_project_migration_chain_webhooks_workers_pgvector(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks", "workers", "pgvector"]})
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    # alembic upgrade head (via the engine fixture inside the suite) must apply 0001->0004.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "0001->0002->0003->0004 chain did not apply:\n" + result.stdout + result.stderr
    )
```

- [ ] **Step 2: Run both** (Docker) → PASS. If `vectors/repository.py` isn't 100% (e.g. `add_embedding` line not hit), confirm the functional test exercises both `add_embedding` and `nearest`. Commit (hook steps). Message: `test(pgvector): Docker acceptance — similarity search + 0001->0004 chain`

---

## Task 4: `mongodb` battery core (client, repo, settings, /health)

**Files:**
- Modify: `src/framework_cli/batteries.py`, `…/pyproject.toml.jinja`, `…/config/settings.py.jinja`, `…/routes/health.py.jinja`
- Create: `…/src/{{package_name}}/{% if "mongodb" in batteries %}mongo{% endif %}/__init__.py`, `client.py`, `repository.py`
- Create: `…/tests/functional/{{ 'test_mongo.py' if 'mongodb' in batteries else '' }}.jinja`
- Test: `tests/test_batteries.py`, `tests/test_copier_runner.py`

- [ ] **Step 1: Failing tests**

`tests/test_batteries.py`: a `test_mongodb_battery_registered` mirroring the pgvector one. `tests/test_copier_runner.py`:
```python
def test_render_with_mongodb_core(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    pkg = dest / "src" / "demo"
    assert (pkg / "mongo" / "client.py").is_file() and (pkg / "mongo" / "repository.py").is_file()
    assert (dest / "tests" / "functional" / "test_mongo.py").is_file()
    assert "pymongo" in (dest / "pyproject.toml").read_text()
    assert "mongo_url" in (pkg / "config" / "settings.py").read_text()
    assert "mongo" in (pkg / "routes" / "health.py").read_text()


def test_render_mongodb_core_clean_without(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "src" / "demo" / "mongo").exists()
    assert "pymongo" not in (dest / "pyproject.toml").read_text()
    assert "mongo_url" not in (dest / "src" / "demo" / "config" / "settings.py").read_text()


def test_render_mongodb_is_ruff_format_clean(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    _assert_ruff_format_clean(dest)
```

- [ ] **Step 2: Red.** `uv run --frozen pytest -q -k mongodb` → FAIL.

- [ ] **Step 3: Register + dep + settings.**
- `batteries.py`: `"mongodb": BatterySpec("mongodb", "MongoDB document store (pymongo) + full observability")`.
- `pyproject.toml.jinja`: gated `{% if "mongodb" in batteries %}    "pymongo>=4.9",\n{% endif %}`.
- `settings.py.jinja`: a gated block (mirror the workers block) with `mongo_url: str = "mongodb://mongo:27017/app"`.

- [ ] **Step 4: Client + repo.** `…/mongo/__init__.py` empty. `…/mongo/client.py` (module-level lazy client, mirrors `db/engine.py`):
```python
from __future__ import annotations

from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

from ..config.settings import get_settings


@lru_cache
def get_client() -> MongoClient:
    return MongoClient(get_settings().mongo_url)


def get_db() -> Database:
    return get_client().get_default_database()
```
`…/mongo/repository.py`:
```python
from collections.abc import Mapping
from typing import Any

from pymongo.database import Database

_COLLECTION = "documents"


def insert_document(db: Database, doc: Mapping[str, Any]) -> str:
    return str(db[_COLLECTION].insert_one(dict(doc)).inserted_id)


def find_documents(db: Database, query: Mapping[str, Any] | None = None) -> list[dict]:
    return list(db[_COLLECTION].find(dict(query or {}), {"_id": 0}))
```

- [ ] **Step 5: `/health` connection check.** In `routes/health.py.jinja`, add a gated block in the `health()` function (mirror the workers redis-liveness block — graceful try/except, close the client):
```jinja
{% if "mongodb" in batteries %}
    from {{ package_name }}.mongo.client import get_client as _mongo_client

    try:
        _mongo_client().admin.command("ping")
        report["mongo"] = {"alive": True}
    except Exception:  # mongo unreachable — degrade, never 500 the probe
        report["mongo"] = {"alive": False}
{% endif %}
```

- [ ] **Step 6: Generated functional test.** `…/tests/functional/{{ 'test_mongo.py' … }}.jinja` against a real mongo via testcontainers (the test starts its own mongo container, since the session Postgres fixture is unrelated):
```python
import pytest


@pytest.fixture(scope="module")
def mongo_db():
    from testcontainers.mongodb import MongoDbContainer

    with MongoDbContainer("mongo:7") as mongo:
        from pymongo import MongoClient

        client = MongoClient(mongo.get_connection_url())
        yield client.get_database("test")


def test_insert_and_find(mongo_db):
    from {{ package_name }}.mongo.repository import find_documents, insert_document

    insert_document(mongo_db, {"kind": "note", "body": "hello"})
    docs = find_documents(mongo_db, {"kind": "note"})
    assert any(d["body"] == "hello" for d in docs)
```
> **[verify]** `testcontainers[mongodb]` must be in the template dev deps (the baseline pins `testcontainers[postgresql]`). Add `testcontainers[mongodb]` gated, or widen the extra, so `MongoDbContainer` imports. Confirm during render.

- [ ] **Step 7: Green + gate + commit.** Message: `feat(mongodb): pymongo client + documents repo + settings + /health check`

---

## Task 5: `mongodb` service + full §5 observability

**Files:** Modify `…/infra/compose/dev.yml.jinja`, `…/infra/observability/prometheus/prometheus.yml.jinja`, `…/.env.example.jinja`, `…/Taskfile.yml.jinja`; create `…/alerts/{{ 'mongodb_alerts.yml' … }}.jinja`, `…/dashboards/{{ 'mongodb.json' … }}.jinja`. Test: `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render tests**
```python
def test_render_mongodb_service_and_obs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "mongo:7" in dev and "mongodb-exporter" in dev
    prom = (dest / "infra" / "observability" / "prometheus" / "prometheus.yml").read_text()
    assert "mongodb-exporter" in prom
    assert "APP_MONGO_URL" in (dest / ".env.example").read_text()
    alerts = dest / "infra" / "observability" / "prometheus" / "alerts" / "mongodb_alerts.yml"
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "mongodb.json"
    assert alerts.exists() and dash.exists()
    import yaml as _y, json as _j
    assert _y.safe_load(alerts.read_text())["groups"][0]["name"] == "mongodb"
    assert _j.loads(dash.read_text())["uid"] == "mongodb"


def test_render_dev_yml_clean_without_mongodb(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert "mongo" not in (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "mongodb" not in (dest / "infra" / "observability" / "prometheus" / "prometheus.yml").read_text()
```

- [ ] **Step 2: Red.**

- [ ] **Step 3: `dev.yml` services** — add a gated block (mirror the workers services block; services indented 2 spaces; `{%- if %}`/`{%- endif %}` byte-identical without the battery):
```jinja
{% if "mongodb" in batteries %}
  mongo:
    image: mongo:7
    profiles: ["dev", "lite"]
    healthcheck:
      test: ["CMD-SHELL", "mongosh --quiet --eval \"db.adminCommand('ping').ok\" | grep -q 1"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    ports:
      - "27017:27017"
    volumes:
      - "mongodata:/data/db"

  mongodb-exporter:
    image: percona/mongodb_exporter:0.43
    profiles: ["dev"]
    command: ["--mongodb.uri=mongodb://mongo:27017", "--collect-all"]
    ports:
      - "9216:9216"
    depends_on:
      mongo:
        condition: service_healthy
{% endif %}
```
Also add `mongodata:` to the compose `volumes:` block, gated the same way. **[verify]** the `mongodb_exporter` image tag + flags; and confirm the `volumes:` top-level key placement.

- [ ] **Step 4: `prometheus.yml` scrape** — gated job (mirror the celery block):
```jinja
{%- if "mongodb" in batteries %}
  - job_name: mongodb
    static_configs:
      - targets: ["mongodb-exporter:9216"]
{%- endif %}
```

- [ ] **Step 5: HYBRID sections** — `.env.example.jinja`: gated `APP_MONGO_URL=mongodb://mongo:27017/app` inside the managed section (mirror the workers entries). `Taskfile.yml.jinja`: a gated `mongo:shell` task (mirror the workers tasks).

- [ ] **Step 6: Alerts + dashboard.** `…/alerts/{{ 'mongodb_alerts.yml' … }}.jinja` — group `mongodb`, a tunable warning rule on exporter availability (**[verify]** metric name against the exporter; a robust default is `up{job="mongodb"} == 0` for `for: 5m`):
```yaml
groups:
- name: mongodb
  rules:
  - alert: MongoDBExporterDown
    expr: up{job="mongodb"} == 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: MongoDB exporter target is down (mongo unreachable or exporter crashed) — app-specific default; tune or remove
```
`…/dashboards/{{ 'mongodb.json' … }}.jinja` — model on `webhooks.json`/`websockets.json`: `uid: "mongodb"`, title "MongoDB", panels for connections + op-rate using exporter metrics (**[verify]** metric names), `__auto`/plain legends, valid JSON.

- [ ] **Step 7: Green + integrity byte-identity (critical — dev.yml/prometheus are LOCKED).** Render baseline + `--with mongodb`; run `framework integrity --ci` (or `from framework_cli.integrity.checker import check`) on each — BOTH green. Confirm baseline `dev.yml`/`prometheus.yml` contain no "mongo". Full gate + commit. Message: `feat(mongodb): mongo + exporter services, scrape target, alerts, dashboard`

---

## Task 6: `mongodb` Docker acceptance

**Files:** Modify `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Add the acceptance test:**
```python
@pytest.mark.skipif(not _docker_available(), reason="uv + docker required: real Mongo + Postgres")
def test_rendered_project_with_mongodb_battery_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})
    assert (dest / "src" / "demo" / "mongo" / "repository.py").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cov = result.stdout + result.stderr
    line = next((ln for ln in cov.splitlines() if "mongo/repository.py" in ln), "")
    assert "100%" in line, f"mongo repo not fully exercised: {line!r}\n{cov}"
```

- [ ] **Step 2: Run (Docker)** → PASS (the test starts its own mongo container via testcontainers; postgres still runs for the baseline suite). Commit. Message: `test(mongodb): Docker acceptance — insert/find round-trip`

---

## Task 7: Downskill both + integrity

**Files:** Test `tests/test_downskill.py`

> No production change expected (the 8a-2/8b-1 mechanisms cover both). Prove it; if a `force=False` refusal occurs, investigate the `usage_references` exclusion rather than switching to `force=True`.

- [ ] **Step 1: Add end-to-end tests** (mirror `test_remove_battery_webhooks_end_to_end`):
```python
def test_remove_battery_pgvector_end_to_end(tmp_path, monkeypatch):
    # render --with pgvector, git init+commit, remove_battery(force=False), assert:
    #   vectors/ gone; pyproject pgvector dep gone; migrations/versions/0004_*.py PRESERVED+warned;
    #   migrations/env.py has no "vectors" import; read_batteries == []; integrity --ci exit 0.
    ...  # follow the webhooks test's structure exactly


def test_remove_battery_mongodb_end_to_end(tmp_path, monkeypatch):
    # render --with mongodb, git init+commit, remove_battery(force=False), assert:
    #   mongo/ gone; pymongo dep gone; mongo_url gone from settings; APP_MONGO_URL gone from
    #   .env.example; dev.yml has no "mongo"; "mongo" gone from health.py; read_batteries == [];
    #   integrity --ci exit 0.
    ...
```
(Write them out fully following the existing webhooks e2e test — the `...` are placeholders for YOU to expand with the real assertions listed in the comments; do not leave literal `...`.)

- [ ] **Step 2: Run** → PASS. If pgvector's migration isn't preserved or a `force` refusal occurs, fix the root cause. Full gate + commit. Message: `test(db): downskill pgvector (migration preserved) + mongodb (no --force); integrity green`

---

## Final review (after all tasks)

Dispatch a final whole-branch reviewer (opus) that **runs the tooling**: full `pytest` (incl. Docker acceptance), `ruff`/`mypy`/`uv lock --check` (no new **framework** dep — pgvector/pymongo are template deps), `uv build`, `framework integrity --ci` on baseline + `--with pgvector` + `--with mongodb` + `--with webhooks,workers,pgvector`, and empirically: the similarity search, the mongo round-trip, the `/health` mongo check, the `0001→0004` chain, and `downskill` of both. Then use **superpowers:finishing-a-development-branch**.

---

## Self-Review

**Spec coverage:** §2 migration helper → Task 1. §3 pgvector (extension/migration/model/repo/no-obs) → Tasks 2-3 (+ conftest pgvector image, the spec's testcontainers note). §4 mongodb (client/demo/settings/service/exporter/scrape/HYBRID/alerts/dashboard/health) → Tasks 4-5-6. §5 composition/integrity/downskill → Tasks 5,7 + final review. §6 testing tiers → across all tasks. Deferred items (§8) untouched.

**Placeholder scan:** Task 7 intentionally leaves the e2e test bodies as commented assertion-lists for the implementer to expand from the existing webhooks template (with an explicit "do not leave literal `...`" instruction) — every other step has concrete code. `[verify]` markers flag third-party specifics (Vector import, Base symbol, pgvector/mongo exporter images + metric names) to confirm in the loop, not guesses to ship blind.

**Type/name consistency:** `migration_down_revisions`/`migration_context` (Task 1) consumed by both render + upskill; `down_revision_workers`/`down_revision_pgvector` context keys match the migration templates; `Embedding`/`add_embedding`/`nearest` consistent across model, repo, test; `get_client`/`get_db`/`insert_document`/`find_documents` consistent across the mongo client, repo, /health, and test; metric `up{job="mongodb"}` matches the prometheus job name `mongodb`.
