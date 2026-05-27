# 8f Slice 2 — DB Paradigm Fan-out (timescaledb + neo4j) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **⚠ PIVOT (2026-05-27): graph = Apache AGE (extension), NOT neo4j (service).** During execution, neo4j was built (Tasks 4–5) then **dropped** — Neo4j Community has no Prometheus exporter that authenticates, so its observability was broken in prod (the dev-only-not-prod defect this slice exists to kill). A spike confirmed Apache AGE multi-stage-copies into the custom `postgres:17` image and runs Cypher. **Tasks 4 & 5 below (neo4j) are SUPERSEDED** by the AGE design — see the spec's "Graph paradigm: Apache AGE" amendment and the **AGE Tasks (4-AGE, 5-AGE) appended at the end of this file**. AGE is an *extension* battery (migration `0006`): Dockerfile multi-stage COPY + `shared_preload_libraries=age` + a `create_graph` migration + a `graph/` Cypher-in-SQL package; obs rides the all-env postgres-exporter (free, prod-correct); no service, no exporter, no settings, no `/health` change, no managed secrets, no `env.py` model import. Task 6 (integrity/combos/downskill) applies with `age` substituted for `neo4j`.

**Goal:** Add the `timescaledb` (extension) and `neo4j` (service) database-paradigm batteries, on a new custom multi-extension Postgres image that also fixes pgvector's latent live-stack gap.

**Architecture:** A templated `infra/docker/postgres.Dockerfile` (apt-installs each present extension) becomes the Postgres image for dev/test/prod compose **and** testcontainers whenever an extension battery is present — so extensions actually load on a live stack, not just in the testcontainers pull. `timescaledb` mirrors the `pgvector` extension archetype (a `0005` hypertable migration, first N>2 migration chain). `neo4j` mirrors the `mongodb` separate-service archetype end-to-end (client + repo + `/health` + dev/`services.yml` service + `observability.yml` exporter + alerts + dashboard).

**Tech Stack:** Copier/Jinja templates, Docker/Compose, PostgreSQL 17 + pgvector + TimescaleDB apt packages, Alembic, SQLAlchemy, the `neo4j` Python bolt driver, Prometheus/Grafana, testcontainers, pytest.

**Spec:** `docs/superpowers/specs/2026-05-26-db-paradigms-slice2-design.md`

**Conventions (read before starting):**
- `src/framework_cli/template/` is **template payload**, not framework source — do not lint/type-check it as framework code. It is validated by rendering (`tests/test_copier_runner.py`) and exercising the rendered project (`tests/acceptance/test_rendered_project.py`).
- Framework quality gate (must be green): `uv run --frozen pytest -q --ignore=tests/acceptance` (fast tier), `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .`, `uv run --frozen mypy src`.
- **The Docker acceptance tier fills `/tmp` and can wedge the sandbox** (root-owned renders). Do NOT run the full `tests/acceptance` suite in one shot; run specific acceptance tests and `rm -rf /tmp/pytest-of-chris/* 2>/dev/null` (sudo if needed) afterward. `docker compose config` (no containers) is the safe merge-validation.
- **Commit-gate hook:** `git commit` is blocked unless `CLAUDE.md` is staged AND its `- **Last updated:**` line was edited. Use **separate** `git add` then `git commit` Bash calls; never combine them; avoid the literal word "commit" elsewhere in a git compound command (it false-trips the hook). For per-task commits in this plan, stage the code/tests; the controller updates `CLAUDE.md` at task boundaries where the hook requires it (or stage a trivial `CLAUDE.md` Last-updated touch with each commit).
- `render_project(dest, {**DATA, "batteries": [...]})` where `DATA = {"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"}` (see the top of `tests/test_copier_runner.py`).
- Integrity check in tests: `from framework_cli.integrity.checker import check`; `from framework_cli.integrity.manifest import write_manifest`; `from framework_cli.source import installed_framework_version` — render, `write_manifest(Path(dest), installed_framework_version())`, then `check(Path(dest), ci=True)` returns a findings list (`[]` == green). (Match the exact imports used by the existing `test_integrity_*` tests — grep `tests/` for `write_manifest` and copy the call shape.)

---

## File Structure

**Framework CLI (`src/framework_cli/`):**
- `migrations.py` — append `timescaledb`/`0005` to `MIGRATION_ORDER` + `REVISIONS` (drift guard already enforces agreement).

**Template payload (`src/framework_cli/template/`):**
- `copier.yml` — add a computed `uses_postgres_extension` variable.
- Create `infra/docker/postgres.Dockerfile.jinja` — `FROM postgres:17` + conditional extension installs.
- Rename `infra/compose/prod.yml` → `prod.yml.jinja`; `infra/compose/staging.yml` → `staging.yml.jinja` (gate the Postgres image).
- Modify `infra/compose/dev.yml.jinja`, `infra/compose/test.yml.jinja` (Postgres build-switch + timescaledb command).
- Modify `tests/conftest.py.jinja` (build the Dockerfile when an extension battery is present).
- Create `migrations/versions/{{ '0005_readings.py' if 'timescaledb' in batteries else '' }}.jinja`.
- Create `src/{{package_name}}/{% if "timescaledb" in batteries %}timeseries{% endif %}/{__init__,models,repository}.py`.
- Create `tests/functional/{{ 'test_timeseries.py' if 'timescaledb' in batteries else '' }}.jinja`.
- Create `src/{{package_name}}/{% if "neo4j" in batteries %}graph{% endif %}/{__init__,client,repository}.py`.
- Create `tests/functional/{{ 'test_graph.py' if 'neo4j' in batteries else '' }}.jinja`.
- Create `infra/observability/prometheus/alerts/{{ 'neo4j_alerts.yml' if 'neo4j' in batteries else '' }}.jinja`.
- Create `infra/observability/grafana/dashboards/{{ 'neo4j.json' if 'neo4j' in batteries else '' }}.jinja`.
- Modify `migrations/env.py.jinja`, `src/{{package_name}}/config/settings.py.jinja`, `src/{{package_name}}/routes/health.py.jinja`, `infra/compose/{dev,services,observability}.yml.jinja`, `infra/observability/prometheus/prometheus.yml.jinja`, `.env.example.jinja`, `Taskfile.yml.jinja`, `pyproject.toml.jinja`, `infra/deploy/strategy.sh`, `infra/deploy/README.md`.

**Framework tests:** `tests/test_copier_runner.py` (render/integrity), `tests/acceptance/test_rendered_project.py` (Docker).

---

## Task 1: Foundation A — custom Postgres image (pgvector) for dev/test/testcontainers

Closes pgvector's live-stack gap: today only the testcontainers image is switched, so a live `task dev`/deploy with pgvector would fail `CREATE EXTENSION vector`. After this task, dev/test compose and testcontainers all use a built image that installs the extension.

**Files:**
- Modify: `src/framework_cli/template/copier.yml`
- Create: `src/framework_cli/template/infra/docker/postgres.Dockerfile.jinja`
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja` (lines 19–20, the `postgres` service `image:`)
- Modify: `src/framework_cli/template/infra/compose/test.yml.jinja` (lines 15–16, the `postgres-test` service `image:`)
- Modify: `src/framework_cli/template/tests/conftest.py.jinja` (the `pg_url` fixture, lines 27–43)
- Test: `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the failing render tests**

Add to `tests/test_copier_runner.py`:

```python
def test_uses_postgres_extension_render_switches_postgres_image(tmp_path):
    """With pgvector, dev/test Postgres build the custom Dockerfile; baseline stays postgres:17."""
    # baseline: plain image, no Dockerfile
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "infra" / "docker" / "postgres.Dockerfile").exists()
    assert "image: postgres:17" in (base / "infra" / "compose" / "dev.yml").read_text()
    assert "image: postgres:17" in (base / "infra" / "compose" / "test.yml").read_text()

    # pgvector: Dockerfile rendered + dev/test build it
    ext = tmp_path / "ext"
    render_project(ext, {**DATA, "batteries": ["pgvector"]})
    dockerfile = ext / "infra" / "docker" / "postgres.Dockerfile"
    assert dockerfile.exists()
    assert "postgresql-17-pgvector" in dockerfile.read_text()
    dev = (ext / "infra" / "compose" / "dev.yml").read_text()
    assert "dockerfile: infra/docker/postgres.Dockerfile" in dev
    assert "image: postgres:17" not in dev  # the postgres service no longer pulls the plain image
    test = (ext / "infra" / "compose" / "test.yml").read_text()
    assert "dockerfile: infra/docker/postgres.Dockerfile" in test
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_uses_postgres_extension_render_switches_postgres_image -q`
Expected: FAIL (Dockerfile not rendered; dev still uses `image: postgres:17`).

- [ ] **Step 3: Add the computed Copier variable**

Append to `src/framework_cli/template/copier.yml`:

```yaml
uses_postgres_extension:
  type: bool
  help: "(computed) any battery that installs a Postgres extension is active"
  default: "{{ 'pgvector' in batteries or 'timescaledb' in batteries }}"
  when: false
```

- [ ] **Step 4: Create the Dockerfile**

Create `src/framework_cli/template/infra/docker/postgres.Dockerfile.jinja`:

```dockerfile
# Custom Postgres image — installs the active extension batteries onto the official image so the
# extensions are available on EVERY stack (dev/test/prod compose + testcontainers), not just a
# prebuilt testcontainers pull. Rendered only when an extension battery is present.
FROM postgres:17
{%- if "pgvector" in batteries %}

# pgvector — vector similarity search (PGDG apt; present on the official postgres image's repo).
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-17-pgvector \
 && rm -rf /var/lib/apt/lists/*
{%- endif %}
```

(TimescaleDB install is added in Task 3.)

- [ ] **Step 5: Switch the dev/test Postgres image**

In `src/framework_cli/template/infra/compose/dev.yml.jinja`, replace **only** the single line `    image: postgres:17` (line 20) — leave `  postgres:` above and `    profiles: ["dev", "lite"]` below unchanged — with this block (preserve the 4-space indentation):

```jinja
{%- if uses_postgres_extension %}
    build:
      context: ../..
      dockerfile: infra/docker/postgres.Dockerfile
{%- else %}
    image: postgres:17
{%- endif %}
```

In `src/framework_cli/template/infra/compose/test.yml.jinja`, replace **only** the `postgres-test` service's `    image: postgres:17` line (line 16) with the identical block above (leave `  postgres-test:` and the `profiles:` line unchanged).

- [ ] **Step 6: Build the Dockerfile in testcontainers**

In `src/framework_cli/template/tests/conftest.py.jinja`, replace the `pg_url` fixture body (the `try:` that constructs `PostgresContainer(...)`, lines 32–34) with:

```jinja
    try:
{%- if uses_postgres_extension %}
        from testcontainers.core.image import DockerImage

        # Build the same custom image the compose stack uses, so tests exercise the real
        # extension install (not a prebuilt pull). cwd is the project root under pytest.
        image = DockerImage(
            path=".",
            dockerfile_path="infra/docker/postgres.Dockerfile",
            tag="{{ package_name }}-postgres:test",
        )
        image.build()
        container = PostgresContainer(str(image), driver="psycopg")
        container.start()
{%- else %}
        container = PostgresContainer("postgres:17", driver="psycopg")
        container.start()
{%- endif %}
```

(Keep the existing `except Exception as exc: pytest.fail(...)` and the `try/finally: yield … container.stop()` that follow.)

- [ ] **Step 7: Run the render tests to verify they pass**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_uses_postgres_extension_render_switches_postgres_image -q`
Expected: PASS.

- [ ] **Step 8: Add the live-stack acceptance test (the explicit gap fix)**

Add to `tests/acceptance/test_rendered_project.py` (mirror the existing `_docker_available` guard + `render_project` + `subprocess` shape used by `test_rendered_project_with_pgvector_battery_passes`):

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: builds the custom Postgres image and runs the live test stack",
)
def test_rendered_pgvector_builds_extension_image_and_migrates(tmp_path: Path):
    """The pgvector project's Postgres image actually installs `vector`, so the 0004
    CREATE EXTENSION migration succeeds against the BUILT image (not just a prebuilt pull).
    Runs the unit+functional gate, which builds infra/docker/postgres.Dockerfile via
    testcontainers and applies alembic upgrade head against it."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})
    assert (dest / "infra" / "docker" / "postgres.Dockerfile").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "pgvector live-build gate failed (CREATE EXTENSION vector on the built image?):\n"
        + result.stdout + result.stderr
    )
```

- [ ] **Step 9: Run the new acceptance test (mind /tmp)**

Run: `uv run --frozen pytest "tests/acceptance/test_rendered_project.py::test_rendered_pgvector_builds_extension_image_and_migrates" -q`
Then: `rm -rf /tmp/pytest-of-chris/* 2>/dev/null; df -h /tmp`
Expected: PASS (the existing `test_rendered_project_with_pgvector_battery_passes` should also still pass — it now builds the image too).

- [ ] **Step 10: Fast gate + commit**

Run: `uv run --frozen pytest -q --ignore=tests/acceptance && uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen mypy src`
Expected: all green.

```bash
git add src/framework_cli/template/copier.yml src/framework_cli/template/infra/docker/postgres.Dockerfile.jinja src/framework_cli/template/infra/compose/dev.yml.jinja src/framework_cli/template/infra/compose/test.yml.jinja src/framework_cli/template/tests/conftest.py.jinja tests/test_copier_runner.py tests/acceptance/test_rendered_project.py
```
Then stage the CLAUDE.md Last-updated touch and `git commit -m "feat(db): custom Postgres image for dev/test/testcontainers — fixes pgvector live-stack gap"`.

---

## Task 2: Foundation B — prod/staging Postgres image switch + deploy build+push guidance

Self-host default: the deploy builds+pushes the custom Postgres image; prod/staging reference `${POSTGRES_IMAGE}` when an extension battery is present, else plain `postgres:17` (byte-identical to today). Managed PG is the documented escape hatch.

**Files:**
- Rename: `src/framework_cli/template/infra/compose/prod.yml` → `prod.yml.jinja`
- Rename: `src/framework_cli/template/infra/compose/staging.yml` → `staging.yml.jinja`
- Modify (after rename): the `postgres` service `image:` in each
- Modify: `src/framework_cli/template/infra/deploy/strategy.sh` (the `__target_place_image` guidance comment, lines 26–37)
- Modify: `src/framework_cli/template/infra/deploy/README.md`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_prod_staging_postgres_image_switches_for_extensions(tmp_path):
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert "image: postgres:17" in (base / "infra" / "compose" / "prod.yml").read_text()
    assert "image: postgres:17" in (base / "infra" / "compose" / "staging.yml").read_text()

    ext = tmp_path / "ext"
    render_project(ext, {**DATA, "batteries": ["timescaledb"]})
    prod = (ext / "infra" / "compose" / "prod.yml").read_text()
    assert "${POSTGRES_IMAGE" in prod and "image: postgres:17" not in prod
    staging = (ext / "infra" / "compose" / "staging.yml").read_text()
    assert "${POSTGRES_IMAGE" in staging
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_prod_staging_postgres_image_switches_for_extensions -q`
Expected: FAIL (`timescaledb` isn't a battery yet AND the files aren't templated). NOTE: this test depends on Task 3 registering `timescaledb`; until then it errors on render. If running Task 2 before Task 3, temporarily use `["pgvector"]` in the test, then switch to `["timescaledb"]` after Task 3. (Recommended: run Tasks 2 and 3 back-to-back; verify this test green at the end of Task 3.)

- [ ] **Step 3: Rename and template prod.yml**

```bash
git mv src/framework_cli/template/infra/compose/prod.yml src/framework_cli/template/infra/compose/prod.yml.jinja
git mv src/framework_cli/template/infra/compose/staging.yml src/framework_cli/template/infra/compose/staging.yml.jinja
```

In `prod.yml.jinja`, replace **only** the `postgres` service's `    image: postgres:17` line (line 26) — leave `  postgres:` above and `    restart: unless-stopped` below unchanged — with (preserve 4-space indentation):

```jinja
{%- if uses_postgres_extension %}
    image: ${POSTGRES_IMAGE:?set POSTGRES_IMAGE to the built+pushed custom Postgres tag (extensions baked in)}
{%- else %}
    image: postgres:17
{%- endif %}
```

Apply the identical single-line replacement to `staging.yml.jinja` (its `postgres` service `image: postgres:17`, line 27).

- [ ] **Step 4: Update the deploy guidance**

In `src/framework_cli/template/infra/deploy/strategy.sh`, extend the `__target_place_image` guidance comment (around lines 30–36) to add, after the existing services/observability merge note:

```bash
# When an extension battery (pgvector/timescaledb) is active, the Postgres service uses the custom
# image (extensions baked in). Build+push it alongside APP_IMAGE and set POSTGRES_IMAGE, e.g.:
#   docker build -f infra/docker/postgres.Dockerfile -t $POSTGRES_IMAGE . && docker push $POSTGRES_IMAGE
# Managed alternative: point APP_DATABASE_URL at a managed Postgres that provides the extensions
# (RDS/Cloud SQL/Timescale Cloud/Supabase) and leave POSTGRES_IMAGE unset / the service unused.
```

(Do not change any executable logic — the `_todo` hooks stay byte-identical.)

- [ ] **Step 5: Update the deploy README**

In `src/framework_cli/template/infra/deploy/README.md`, add a short subsection "Custom Postgres image (extension batteries)" documenting: extension batteries bake `vector`/`timescaledb` into a custom image via `infra/docker/postgres.Dockerfile`; self-host builds+pushes it and sets `POSTGRES_IMAGE`; managed PG with the extensions is the escape hatch (set `APP_DATABASE_URL`).

- [ ] **Step 6: Verify render test passes**

Run (after Task 3 registers timescaledb, or with `["pgvector"]` temporarily): `uv run --frozen pytest tests/test_copier_runner.py::test_prod_staging_postgres_image_switches_for_extensions -q`
Expected: PASS.

- [ ] **Step 7: docker compose config merge-validation (safe; no containers)**

Render a pgvector project, then from its root:
```bash
APP_IMAGE=demo:ci POSTGRES_PASSWORD=x POSTGRES_IMAGE=demo-pg:ci docker compose -f infra/compose/prod.yml config
```
Expected: exit 0; the `postgres` service `image` resolves to `demo-pg:ci`.

- [ ] **Step 8: Fast gate + commit**

Run the fast gate (Task 1 Step 10 command). Stage the renamed/edited files + test + CLAUDE.md touch; `git commit -m "feat(db): prod/staging use the custom Postgres image when extensions are active (build+push, managed escape hatch)"`.

---

## Task 3: timescaledb battery (extension archetype)

**Files:**
- Modify: `src/framework_cli/migrations.py` (lines 14–16)
- Modify: `src/framework_cli/template/infra/docker/postgres.Dockerfile.jinja`
- Modify: `src/framework_cli/template/infra/compose/{dev,test,prod,staging}.yml.jinja` (Postgres `command:` for timescaledb)
- Modify: `src/framework_cli/template/tests/conftest.py.jinja` (timescaledb `with_command`)
- Create: `src/framework_cli/template/migrations/versions/{{ '0005_readings.py' if 'timescaledb' in batteries else '' }}.jinja`
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "timescaledb" in batteries %}timeseries{% endif %}/{__init__.py,models.py,repository.py}`
- Modify: `src/framework_cli/template/migrations/env.py.jinja` (line 9 area)
- Create: `src/framework_cli/template/tests/functional/{{ 'test_timeseries.py' if 'timescaledb' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the failing migrations + render tests**

Add to `tests/test_copier_runner.py`:

```python
def test_timescaledb_migration_ordering():
    from framework_cli.migrations import migration_down_revisions
    # timescaledb alone chains off baseline; with pgvector it chains off 0004 (N>2).
    assert migration_down_revisions(["timescaledb"]) == {"timescaledb": "0001"}
    assert migration_down_revisions(["pgvector", "timescaledb"]) == {
        "pgvector": "0001", "timescaledb": "0004",
    }


def test_render_timescaledb_battery(tmp_path):
    dest = tmp_path / "ts"
    render_project(dest, {**DATA, "batteries": ["timescaledb"]})
    assert (dest / "src" / "demo" / "timeseries" / "repository.py").exists()
    mig = (dest / "migrations" / "versions" / "0005_readings.py").read_text()
    assert "create_hypertable" in mig
    assert 'down_revision = "0001"' in mig
    df = (dest / "infra" / "docker" / "postgres.Dockerfile").read_text()
    assert "timescaledb-2-postgresql-17" in df
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "shared_preload_libraries=timescaledb" in dev
    # env.py imports the timeseries models
    assert "timeseries import models" in (dest / "migrations" / "env.py").read_text()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_timescaledb_migration_ordering tests/test_copier_runner.py::test_render_timescaledb_battery -q`
Expected: FAIL (`timescaledb` unknown → empty `migration_down_revisions`; files not rendered).

- [ ] **Step 3: Register the migration**

In `src/framework_cli/migrations.py`, update lines 14–16:

```python
MIGRATION_ORDER: tuple[str, ...] = ("webhooks", "workers", "pgvector", "timescaledb")
REVISIONS: dict[str, str] = {
    "webhooks": "0002", "workers": "0003", "pgvector": "0004", "timescaledb": "0005",
}
```

- [ ] **Step 4: Extend the Dockerfile with TimescaleDB**

Append to `src/framework_cli/template/infra/docker/postgres.Dockerfile.jinja` (after the pgvector block):

```dockerfile
{%- if "timescaledb" in batteries %}

# TimescaleDB — hypertables / time-series (Timescale apt repo; not in PGDG). Requires
# shared_preload_libraries=timescaledb at runtime (set via the compose `command:`).
RUN apt-get update \
 && apt-get install -y --no-install-recommends gnupg wget lsb-release ca-certificates \
 && echo "deb https://packagecloud.io/timescale/timescaledb/debian/ $(lsb_release -cs) main" \
      > /etc/apt/sources.list.d/timescaledb.list \
 && wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey \
      | gpg --dearmor -o /etc/apt/trusted.gpg.d/timescaledb.gpg \
 && apt-get update \
 && apt-get install -y --no-install-recommends timescaledb-2-postgresql-17 \
 && rm -rf /var/lib/apt/lists/*
{%- endif %}
```

- [ ] **Step 5: Set shared_preload_libraries in the Postgres services**

In each of `dev.yml.jinja` (the `postgres` service), `test.yml.jinja` (`postgres-test`), `prod.yml.jinja` and `staging.yml.jinja` (the `postgres` service), add — right after the `build:`/`image:` block and before `profiles:`/`restart:` — a gated command:

```jinja
{%- if "timescaledb" in batteries %}
    command: ["postgres", "-c", "shared_preload_libraries=timescaledb"]
{%- endif %}
```

In `tests/conftest.py.jinja`, inside the `uses_postgres_extension` branch (after `container = PostgresContainer(str(image), driver="psycopg")` and before `container.start()`), add:

```jinja
{%- if "timescaledb" in batteries %}
        container = container.with_command("postgres -c shared_preload_libraries=timescaledb")
{%- endif %}
```

- [ ] **Step 6: Create the 0005 migration**

Create `src/framework_cli/template/migrations/versions/{{ '0005_readings.py' if 'timescaledb' in batteries else '' }}.jinja`:

```python
"""timescaledb readings hypertable

Revision ID: 0005
Revises: {{ down_revision_timescaledb }}

"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "{{ down_revision_timescaledb }}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.create_table(
        "readings",
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("item_id", "time"),
    )
    # The hypertable partition column (time) is part of the PK — TimescaleDB requires any
    # unique/primary key to include the partitioning column.
    op.execute("SELECT create_hypertable('readings', 'time')")


def downgrade() -> None:
    # Drop the table; leave the timescaledb extension (dropping a shared extension is destructive).
    op.drop_table("readings")
```

- [ ] **Step 7: Create the timeseries package**

Create `src/framework_cli/template/src/{{package_name}}/{% if "timescaledb" in batteries %}timeseries{% endif %}/__init__.py` (empty).

Create `.../timeseries/models.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class Reading(Base):
    __tablename__ = "readings"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
```

Create `.../timeseries/repository.py`:

```python
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import Reading


def add_reading(session: Session, item_id: int, time: datetime, value: float) -> Reading:
    row = Reading(item_id=item_id, time=time, value=value)
    session.add(row)
    session.commit()
    return row


def bucketed_averages(session: Session, bucket: str = "1 hour") -> Sequence[tuple]:
    """Average value per time bucket (TimescaleDB time_bucket), oldest first."""
    rows = session.execute(
        text(
            "SELECT time_bucket(CAST(:bucket AS interval), time) AS bucket, avg(value) AS avg "
            "FROM readings GROUP BY bucket ORDER BY bucket"
        ),
        {"bucket": bucket},
    )
    return [(r.bucket, float(r.avg)) for r in rows]
```

- [ ] **Step 8: Import the models in env.py**

In `src/framework_cli/template/migrations/env.py.jinja`, after the pgvector import line (line 9), add:

```jinja
{% if "timescaledb" in batteries %}from {{ package_name }}.timeseries import models as _timeseries_models  # noqa: F401
{% endif %}
```

(Match the existing `{% if … %}…{% endif %}` chaining style on lines 7–10 so whitespace stays clean.)

- [ ] **Step 9: Create the functional test**

Create `src/framework_cli/template/tests/functional/{{ 'test_timeseries.py' if 'timescaledb' in batteries else '' }}.jinja`:

```python
from datetime import datetime, timedelta, timezone

from {{ package_name }}.db.repository import create_item
from {{ package_name }}.timeseries.repository import add_reading, bucketed_averages


def test_bucketed_averages_aggregates_by_time(db_session):
    item = create_item(db_session, "sensor")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    add_reading(db_session, item.id, base, 10.0)
    add_reading(db_session, item.id, base + timedelta(minutes=10), 20.0)
    add_reading(db_session, item.id, base + timedelta(hours=2), 5.0)
    buckets = bucketed_averages(db_session, "1 hour")
    assert len(buckets) == 2  # two distinct hourly buckets
    assert buckets[0][1] == 15.0  # avg(10, 20)
```

- [ ] **Step 10: Run render + migrations tests**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_timescaledb_migration_ordering tests/test_copier_runner.py::test_render_timescaledb_battery tests/test_copier_runner.py::test_prod_staging_postgres_image_switches_for_extensions -q`
Expected: PASS (and the Task-2 prod/staging test now uses `["timescaledb"]`).

- [ ] **Step 11: Add the timescaledb live acceptance test**

Add to `tests/acceptance/test_rendered_project.py` (mirror the pgvector acceptance test):

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: builds the TimescaleDB image and runs the live test stack",
)
def test_rendered_timescaledb_battery_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["timescaledb"]})
    assert (dest / "migrations" / "versions" / "0005_readings.py").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "timescaledb gate failed (create_hypertable / time_bucket on the built image?):\n"
        + result.stdout + result.stderr
    )
```

- [ ] **Step 12: Run the acceptance test (mind /tmp)**

Run: `uv run --frozen pytest "tests/acceptance/test_rendered_project.py::test_rendered_timescaledb_battery_passes" -q`
Then: `rm -rf /tmp/pytest-of-chris/* 2>/dev/null; df -h /tmp`
Expected: PASS.

- [ ] **Step 13: Fast gate + commit**

Run the fast gate. Stage all timescaledb files + tests + CLAUDE.md touch; `git commit -m "feat(db): timescaledb battery — hypertable migration (0005, first N>2 chain) + time_bucket repo"`.

---

## Task 4: neo4j battery — app side (package, settings, deps, /health, env, Taskfile, functional test)

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "neo4j" in batteries %}graph{% endif %}/{__init__.py,client.py,repository.py}`
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja` (after the mongodb block, ~line 53)
- Modify: `src/framework_cli/template/pyproject.toml.jinja` (conditional `neo4j` dep — match how `pymongo`/`pgvector` are gated)
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja` (after the mongodb block, ~line 46)
- Modify: `src/framework_cli/template/.env.example.jinja` (after the mongodb block, ~line 21)
- Modify: `src/framework_cli/template/Taskfile.yml.jinja` (after the `mongo:shell` block, ~line 150)
- Create: `src/framework_cli/template/tests/functional/{{ 'test_graph.py' if 'neo4j' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_neo4j_battery_app_side(tmp_path):
    dest = tmp_path / "n4"
    render_project(dest, {**DATA, "batteries": ["neo4j"]})
    assert (dest / "src" / "demo" / "graph" / "client.py").exists()
    assert (dest / "src" / "demo" / "graph" / "repository.py").exists()
    settings = (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "neo4j_url" in settings
    health = (dest / "src" / "demo" / "routes" / "health.py").read_text()
    assert "neo4j" in health and "verify_connectivity" in health
    assert "neo4j" in (dest / "pyproject.toml").read_text()
    assert "APP_NEO4J_PASSWORD" in (dest / ".env.example").read_text()
    assert (dest / "tests" / "functional" / "test_graph.py").exists()
    # baseline omits all of it
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "src" / "demo" / "graph").exists()
    assert "neo4j_url" not in (base / "src" / "demo" / "config" / "settings.py").read_text()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_render_neo4j_battery_app_side -q`
Expected: FAIL.

- [ ] **Step 3: Create the graph package**

`.../graph/__init__.py` (empty).

`.../graph/client.py`:

```python
from __future__ import annotations

from functools import lru_cache

from neo4j import Driver, GraphDatabase

from ..config.settings import get_settings


@lru_cache
def get_driver() -> Driver:
    s = get_settings()
    return GraphDatabase.driver(s.neo4j_url, auth=(s.neo4j_user, s.neo4j_password))
```

`.../graph/repository.py`:

```python
from __future__ import annotations

from neo4j import Driver


def relate(driver: Driver, src: str, dst: str, kind: str = "KNOWS") -> None:
    """Create two Person nodes (by name) and a typed relationship between them."""
    with driver.session() as session:
        session.run(
            "MERGE (a:Person {name: $src}) MERGE (b:Person {name: $dst}) "
            f"MERGE (a)-[:{kind}]->(b)",
            src=src,
            dst=dst,
        )


def neighbors(driver: Driver, name: str) -> list[str]:
    """Names directly reachable from `name` by any outgoing relationship."""
    with driver.session() as session:
        result = session.run(
            "MATCH (a:Person {name: $name})-->(b:Person) RETURN b.name AS name ORDER BY name",
            name=name,
        )
        return [record["name"] for record in result]
```

- [ ] **Step 4: Add settings**

In `settings.py.jinja`, after the mongodb block (after line 53, before the `@property` on line 55), add:

```jinja
{%- if "neo4j" in batteries %}

    # Neo4j (bolt). The Compose stack injects APP_NEO4J_* ; defaults point at the dev service.
    neo4j_url: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j_dev_password"
{%- endif %}
```

- [ ] **Step 5: Add the conditional dependency**

In `pyproject.toml.jinja`, add the `neo4j` driver to the conditional dependency list exactly where `pymongo`/`pgvector` are gated (grep `pyproject.toml.jinja` for `pymongo` and mirror the `{% if … %}` form):

```jinja
{% if "neo4j" in batteries %}    "neo4j>=5.0",
{% endif %}
```

- [ ] **Step 6: Add the /health ping**

In `health.py.jinja`, after the mongodb block (after line 46), add:

```jinja
{% if "neo4j" in batteries %}
    from {{ package_name }}.graph.client import get_driver as _neo4j_driver

    try:
        _neo4j_driver().verify_connectivity()
        report["neo4j"] = {"alive": True}
    except Exception:  # neo4j unreachable — degrade, never 500 the probe
        report["neo4j"] = {"alive": False}
{% endif %}
```

- [ ] **Step 7: Add the .env.example managed entry**

In `.env.example.jinja`, after the mongodb block (after line 21), add:

```jinja
{% if "neo4j" in batteries %}# Neo4j (bolt) — in-network default; override per environment. NEO4J_AUTH seeds the container.
APP_NEO4J_URL=bolt://neo4j:7687
APP_NEO4J_USER=neo4j
APP_NEO4J_PASSWORD=neo4j_dev_password
{% endif %}
```

- [ ] **Step 8: Add the Taskfile shell task**

In `Taskfile.yml.jinja`, after the `mongo:shell` block (after line 150), add:

```jinja
{% endif %}{% if "neo4j" in batteries %}
  neo4j:shell:
    desc: Open a cypher-shell against the dev Neo4j.
    cmds:
      - docker compose -f infra/compose/dev.yml exec neo4j cypher-shell -u neo4j -p neo4j_dev_password
```

(Verify the surrounding `{% if %}/{% endif %}` nesting — the mongodb section ends with `{% endif %}`; the neo4j block must chain correctly. Render and diff to confirm no stray markers.)

- [ ] **Step 9: Create the functional test**

Create `tests/functional/{{ 'test_graph.py' if 'neo4j' in batteries else '' }}.jinja`:

```python
import pytest


@pytest.fixture(scope="module")
def neo4j_driver():
    from testcontainers.neo4j import Neo4jContainer

    with Neo4jContainer("neo4j:5") as neo4j:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            neo4j.get_connection_url(), auth=("neo4j", neo4j.password)
        )
        yield driver
        driver.close()


def test_relate_and_neighbors(neo4j_driver):
    from {{ package_name }}.graph.repository import neighbors, relate

    relate(neo4j_driver, "alpha", "beta")
    assert "beta" in neighbors(neo4j_driver, "alpha")
```

(Add `testcontainers[neo4j]` to the conditional test deps the same way `testcontainers[mongodb]` is gated — grep `pyproject.toml.jinja` for `testcontainers` and mirror.)

- [ ] **Step 10: Run the render test**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_render_neo4j_battery_app_side -q`
Expected: PASS.

- [ ] **Step 11: Add the neo4j functional acceptance test**

Add to `tests/acceptance/test_rendered_project.py`:

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: real Neo4j + Postgres",
)
def test_rendered_neo4j_battery_passes(tmp_path: Path):
    # Renders a neo4j project, then runs unit+functional (70% gate) so test_graph.py runs
    # relate()/neighbors() against a real Neo4jContainer("neo4j:5").
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["neo4j"]})
    assert (dest / "src" / "demo" / "graph" / "repository.py").exists()
    assert (dest / "tests" / "functional" / "test_graph.py").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the neo4j battery project:\n"
        + result.stdout + result.stderr
    )
    cov = result.stdout + result.stderr
    line = next((ln for ln in cov.splitlines() if "graph/repository.py" in ln), "")
    assert "100%" in line, (
        f"graph repo not fully exercised; coverage line: {line!r}\n"
        "Expected 100% of graph/repository.py — did test_graph.py run?\n" + cov
    )
```

- [ ] **Step 12: Run it (mind /tmp)**

Run: `uv run --frozen pytest "tests/acceptance/test_rendered_project.py::test_rendered_neo4j_battery_passes" -q`
Then: `rm -rf /tmp/pytest-of-chris/* 2>/dev/null; df -h /tmp`
Expected: PASS.

- [ ] **Step 13: Fast gate + commit**

Run the fast gate. Stage graph package + settings/health/env/Taskfile/pyproject + tests + CLAUDE.md touch; `git commit -m "feat(db): neo4j battery (app side) — bolt client + graph repo + /health ping + functional test"`.

---

## Task 5: neo4j battery — infra (compose services, exporter, scrape, alerts, dashboard)

**Files:**
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja` (add `neo4j` service + `neo4jdata` volume)
- Modify: `src/framework_cli/template/infra/compose/services.yml.jinja` (add prod `neo4j` service + volume)
- Modify: `src/framework_cli/template/infra/compose/observability.yml.jinja` (add `neo4j-exporter`)
- Modify: `src/framework_cli/template/infra/observability/prometheus/prometheus.yml.jinja` (add `neo4j` scrape job)
- Create: `src/framework_cli/template/infra/observability/prometheus/alerts/{{ 'neo4j_alerts.yml' if 'neo4j' in batteries else '' }}.jinja`
- Create: `src/framework_cli/template/infra/observability/grafana/dashboards/{{ 'neo4j.json' if 'neo4j' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_neo4j_battery_infra(tmp_path):
    dest = tmp_path / "n4"
    render_project(dest, {**DATA, "batteries": ["neo4j"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "neo4j:5" in dev and "neo4jdata" in dev
    services = (dest / "infra" / "compose" / "services.yml").read_text()
    assert "neo4j:5" in services
    obs = (dest / "infra" / "compose" / "observability.yml").read_text()
    assert "neo4j-exporter" in obs
    prom = (dest / "infra" / "observability" / "prometheus" / "prometheus.yml").read_text()
    assert 'job_name: neo4j' in prom
    assert (dest / "infra" / "observability" / "prometheus" / "alerts" / "neo4j_alerts.yml").exists()
    assert (dest / "infra" / "observability" / "grafana" / "dashboards" / "neo4j.json").exists()
    # byte-identical without the battery: these LOCKED files must equal the baseline render
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    for f in ["infra/compose/dev.yml", "infra/compose/services.yml",
              "infra/compose/observability.yml", "infra/observability/prometheus/prometheus.yml"]:
        # only assert the neo4j additions are absent (full byte-identity is checked by integrity)
        assert "neo4j" not in (base / f).read_text()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_render_neo4j_battery_infra -q`
Expected: FAIL.

- [ ] **Step 3: Add the dev neo4j service**

In `dev.yml.jinja`, add a gated block after the mongodb block (after line 78, before the workers block) — mirror the mongo service shape:

```jinja
{%- if "neo4j" in batteries %}

  neo4j:
    image: neo4j:5
    profiles: ["dev", "lite"]
    environment:
      NEO4J_AUTH: "neo4j/neo4j_dev_password"
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p neo4j_dev_password 'RETURN 1' || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 20s
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - "neo4jdata:/data"
{%- endif %}
```

In the `volumes:` block at the bottom of `dev.yml.jinja` (lines 141–145), add a gated `neo4jdata: {}` (mirror the `mongodata`/`redisdata` gating, keeping the existing whitespace-control style):

```jinja
{% if "neo4j" in batteries %}  neo4jdata: {}
{% endif %}
```

- [ ] **Step 4: Add the prod neo4j service**

In `services.yml.jinja`, extend the outer guard to include neo4j and add the service. Change the top guard (line 6) to:

```jinja
{%- if "mongodb" in batteries or "workers" in batteries or "neo4j" in batteries %}
```

Add, after the mongodb block (after line 20):

```jinja
{%- if "neo4j" in batteries %}
  neo4j:
    image: neo4j:5
    restart: unless-stopped
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD:?set NEO4J_PASSWORD in the target environment}"
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p \"$NEO4J_PASSWORD\" 'RETURN 1' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s
    volumes:
      - "neo4jdata:/data"
{%- endif %}
```

In the `services.yml.jinja` `volumes:` block (lines 69–75), add a gated `neo4jdata: {}`:

```jinja
{%- if "neo4j" in batteries %}
  neo4jdata: {}
{%- endif %}
```

- [ ] **Step 5: Add the exporter**

In `observability.yml.jinja`, after the mongodb-exporter block (after line 103), add:

```jinja
{%- if "neo4j" in batteries %}

  neo4j-exporter:
    image: comol/neo4jexporter:latest  # community exporter (Neo4j Community has no native Prometheus)
    environment:
      NEO4J_URI: "bolt://neo4j:7687"
      NEO4J_USERNAME: "neo4j"
      NEO4J_PASSWORD: "neo4j_dev_password"
    ports:
      - "9975:9975"
    depends_on:
      neo4j:
        condition: service_healthy
{%- endif %}
```

NOTE: pin a working tag/digest during Step 8 (verify the image runs and exposes `/metrics`); `:latest` is a placeholder to replace before commit. The exporter's exact env var names depend on the chosen image — confirm them against the image's docs and adjust.

- [ ] **Step 6: Add the scrape job**

In `prometheus.yml.jinja`, after the mongodb block (after line 33), add:

```jinja
{%- if "neo4j" in batteries %}
  - job_name: neo4j
    static_configs:
      - targets: ["neo4j-exporter:9975"]
{%- endif %}
```

(Match the exporter's actual metrics port from Step 5.)

- [ ] **Step 7: Add alerts + dashboard**

Create `.../alerts/{{ 'neo4j_alerts.yml' if 'neo4j' in batteries else '' }}.jinja` (mirror `mongodb_alerts.yml`):

```yaml
groups:
- name: neo4j
  rules:
  - alert: Neo4jExporterDown
    expr: up{job="neo4j"} == 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: Neo4j exporter target is down (neo4j unreachable or exporter crashed) — app-specific default; tune or remove
```

Create `.../dashboards/{{ 'neo4j.json' if 'neo4j' in batteries else '' }}.jinja` — a minimal valid Grafana dashboard (one "Neo4j up" stat panel). Verify the `datasource`/`schemaVersion`/provisioning shape matches the existing `mongodb.json` (open it and copy the envelope) so Grafana's file provisioner loads it; then the body is:

```json
{
  "title": "Neo4j",
  "uid": "neo4j",
  "schemaVersion": 39,
  "timezone": "",
  "panels": [
    {
      "id": 1,
      "type": "stat",
      "title": "Neo4j up",
      "gridPos": {"h": 6, "w": 8, "x": 0, "y": 0},
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "targets": [
        {"refId": "A", "expr": "up{job=\"neo4j\"}", "datasource": {"type": "prometheus", "uid": "prometheus"}}
      ]
    }
  ]
}
```

(If `mongodb.json` uses a different `datasource.uid` or wraps panels differently, match it exactly — a mismatched datasource uid makes the panel render "No data".)

- [ ] **Step 8: docker compose config merge-validations (safe) + verify the exporter image**

Render a neo4j project. From its root:
```bash
docker compose -f infra/compose/dev.yml --profile dev config        # neo4j service present, healthcheck valid
APP_IMAGE=demo:ci POSTGRES_PASSWORD=x NEO4J_PASSWORD=p docker compose -f infra/compose/prod.yml -f infra/compose/services.yml -f infra/compose/observability.yml config  # neo4j + neo4j-exporter present, depends_on resolves
```
Verify the exporter image actually runs and serves metrics (pin its tag/port/env in Steps 5–6 from this):
```bash
docker run --rm -d --name n4e -e NEO4J_URI=bolt://host.docker.internal:7687 comol/neo4jexporter:<tag>; sleep 5; curl -s localhost:<port>/metrics | head; docker rm -f n4e
```
Expected: configs exit 0; exporter exposes Prometheus metrics. Replace `:latest` with the confirmed tag.

- [ ] **Step 9: Run the render test**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_render_neo4j_battery_infra -q`
Expected: PASS.

- [ ] **Step 10: Fast gate + commit**

Run the fast gate. Stage compose/obs/prometheus/alerts/dashboard + test + CLAUDE.md touch; `git commit -m "feat(db): neo4j battery (infra) — dev+prod service, community exporter, scrape, alert, dashboard"`.

---

## Task 6: Integrity, cross-battery combinations, and downskill

**Files:**
- Test: `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write integrity tests across battery combinations**

Add to `tests/test_copier_runner.py` (match the existing `test_integrity_*` helpers' exact imports/call shape — grep for `write_manifest` + `check`):

```python
import pytest
from framework_cli.integrity.checker import check
from framework_cli.integrity.manifest import write_manifest
from framework_cli.source import installed_framework_version


@pytest.mark.parametrize("batteries", [
    [], ["pgvector"], ["timescaledb"], ["neo4j"],
    ["pgvector", "timescaledb"], ["timescaledb", "neo4j"],
    ["pgvector", "timescaledb", "neo4j"], ["workers", "mongodb", "neo4j", "timescaledb"],
])
def test_integrity_green_for_slice2_combos(tmp_path, batteries):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": batteries})
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []
```

- [ ] **Step 2: Run to verify it passes (or surfaces byte-identity drift)**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_integrity_green_for_slice2_combos -q`
Expected: PASS. If any combo fails, the cause is almost always a stray newline in a conditionally-edited LOCKED file (`dev.yml`/`prod.yml`/`staging.yml`/`services.yml`/`observability.yml`/`prometheus.yml`) leaking into a render — fix with Jinja whitespace control (`{%-`/`-%}`) until baseline and each combo are green.

- [ ] **Step 3: Write the downskill tests**

Add to `tests/test_copier_runner.py` (match the existing `test_integrity_workers` downskill shape — grep for `remove_battery` / `downskill`):

```python
def test_downskill_timescaledb_preserves_migration_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["timescaledb"]})
    write_manifest(dest, installed_framework_version())
    # git-init so downskill can operate (it requires a tracked project — mirror existing tests)
    _git_init_commit(dest)  # reuse the helper the existing downskill tests use
    remove_battery(dest, "timescaledb", force=False)
    # the 0005 migration is preserved (a DB may be at that revision), the package is gone
    assert (dest / "migrations" / "versions" / "0005_readings.py").exists()
    assert not (dest / "src" / "demo" / "timeseries").exists()
    assert check(dest, ci=True) == []


def test_downskill_neo4j_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["neo4j"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "neo4j", force=False)
    assert not (dest / "src" / "demo" / "graph").exists()
    assert "neo4j" not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert check(dest, ci=True) == []
```

(If the existing downskill tests use a different git-init helper name, use theirs verbatim.)

- [ ] **Step 4: Run downskill tests**

Run: `uv run --frozen pytest tests/test_copier_runner.py -k "downskill_timescaledb or downskill_neo4j" -q`
Expected: PASS. If `remove_battery` demands `--force`, the cause is a usage-reference false positive on a gated shared file — confirm the 8b-1 byte-identity exclusion covers the new gated files (`settings.py`/`health.py`/`env.py`); if a genuinely builder-shared file trips it, that's expected and the test should assert the warning rather than force.

- [ ] **Step 5: Add a combined-battery acceptance test (N>2 chain live)**

Add to `tests/acceptance/test_rendered_project.py`:

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: pgvector+timescaledb migration chain on the built image",
)
def test_rendered_pgvector_timescaledb_chain_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector", "timescaledb"]})
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "pgvector+timescaledb chain gate failed (0001->0004->0005 on the built image?):\n"
        + result.stdout + result.stderr
    )
```

- [ ] **Step 6: Run it (mind /tmp)**

Run: `uv run --frozen pytest "tests/acceptance/test_rendered_project.py::test_rendered_pgvector_timescaledb_chain_passes" -q`
Then: `rm -rf /tmp/pytest-of-chris/* 2>/dev/null; df -h /tmp`
Expected: PASS.

- [ ] **Step 7: Full fast gate + commit**

Run: `uv run --frozen pytest -q --ignore=tests/acceptance && uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen mypy src`
Expected: all green. Stage tests + CLAUDE.md touch; `git commit -m "test(db): integrity across slice-2 battery combos + downskill + N>2 migration chain"`.

---

## Final Review (controller, after all tasks)

Dispatch an opus whole-branch reviewer that RUNS the tooling (see the SVC-PROD final-review pattern). It must:
- Run the fast gate (`pytest -q --ignore=tests/acceptance`, ruff check, ruff format --check, mypy src) — report counts.
- `uv lock --check` (no new FRAMEWORK dep — `neo4j`/`testcontainers[neo4j]` are template-only) + `uv build`.
- Empirically verify (safe `docker compose config`, no container floods): pgvector/timescaledb dev Postgres uses `build:`; prod/staging Postgres uses `${POSTGRES_IMAGE}` with an extension; neo4j present in dev + prod (`services.yml`) with its exporter in `observability.yml` and `depends_on` resolving; baseline renders use plain `postgres:17` and contain no `neo4j`.
- Integrity green across all combos in Task 6 (new + downskill).
- Run a BOUNDED set of the new live acceptance tests (one or two, with `/tmp` cleanup between) — confirm the extensions install on the built image and the neo4j round-trip works. Do NOT run the full acceptance tier (the /tmp wedge risk).
- **Explicitly re-check the OBS/SVC live-stack gap class**: confirm no existing live-stack acceptance test breaks because of the Postgres image switch (read `tests/acceptance/test_rendered_project.py` — the baseline live-stack tests render no batteries → plain `postgres:17`, unaffected).
- Verdict: READY TO MERGE or NOT READY + severity-tagged blockers with file + fix.

Then proceed to `superpowers:finishing-a-development-branch`.

---

## Notes & Risks (for implementers)

- **`neo4j-exporter` image is the one genuine unknown.** Community Neo4j has no native Prometheus endpoint. The plan uses `comol/neo4jexporter` but you MUST verify a working tag, metrics port, and env var names in Task 5 Step 8 and pin them before committing. The `Neo4jExporterDown` alert keys on scrape liveness (`up{job="neo4j"} == 0`), so it's robust regardless of which exporter/metrics you land on.
- **TimescaleDB apt repo** (`packagecloud.io/timescale/timescaledb`) is the install path on the official `postgres:17` image. If the repo/key URLs have changed, fix them in Task 3 Step 4; the live acceptance test (Step 12) is the proof.
- **testcontainers image build** (Task 1 Step 6) requires Docker build access + network (apt). The `_docker_available` guard skips these tests where Docker is absent. `DockerImage` API: confirm against the installed `testcontainers` version (`DockerImage(path=..., dockerfile_path=..., tag=...).build()`); adjust if the signature differs.
- **No baseline manifest shift** is a hard invariant: a no-battery render must stay byte-identical (Task 6 integrity `[]` on `batteries=[]`). The renamed `prod.yml.jinja`/`staging.yml.jinja` must render byte-identical to the old `prod.yml`/`staging.yml` for `batteries=[]`.
- **Whitespace control** in the conditionally-edited LOCKED compose/prometheus files is the most common failure mode (the 8c regression class) — use `{%-`/`-%}` and let Task 6 integrity be the guard.

---

# AGE Tasks (live — supersede neo4j Tasks 4–5)

Graph is delivered as the **`age` extension battery** (Apache AGE on Postgres), a third extension alongside pgvector/timescaledb. Spike-confirmed: a multi-stage `COPY` of `age.so` + `age--1.6.0.sql` + `age.control` from `apache/age:release_PG17_1.6.0` into our `FROM postgres:17` image builds; `CREATE EXTENSION age` loads with `shared_preload_libraries=age`; `create_graph` + a Cypher `CREATE`/`MATCH` round-trip works.

**NB — re-register timescaledb:** the dropped neo4j commits had also registered `timescaledb` in `batteries.py` (a T3 gap fix). Task 4-AGE re-adds both `timescaledb` and `age` registration + their `test_*_battery_registered` guards.

## Task 4-AGE: AGE foundation — Dockerfile multi-stage COPY + shared_preload join + 0006 migration + registration

**Files:** `copier.yml` (add `age` to `uses_postgres_extension`), `infra/docker/postgres.Dockerfile.jinja` (AGE multi-stage block), `infra/compose/{dev,test,prod,staging}.yml.jinja` + `tests/conftest.py.jinja` (generalize the timescaledb `shared_preload_libraries` command to a comma-joined list over {timescaledb, age}), new `migrations/versions/{{ '0006_graph.py' if 'age' in batteries else '' }}.jinja`, `src/framework_cli/migrations.py` (`age`→`0006`), `src/framework_cli/batteries.py` (register `age` + `timescaledb`), `tests/test_batteries.py` (+ `test_age_battery_registered`, `test_timescaledb_battery_registered`), `tests/test_copier_runner.py`.

- `uses_postgres_extension` default → `"{{ 'pgvector' in batteries or 'timescaledb' in batteries or 'age' in batteries }}"`.
- Dockerfile AGE block (gated `{%- if "age" in batteries %}`):
  ```dockerfile
  # Apache AGE — openCypher graph queries on Postgres (multi-stage COPY of the prebuilt PG17
  # extension; AGE has no apt package). Requires shared_preload_libraries=age at runtime.
  COPY --from=apache/age:release_PG17_1.6.0 /usr/lib/postgresql/17/lib/age.so /usr/lib/postgresql/17/lib/age.so
  COPY --from=apache/age:release_PG17_1.6.0 /usr/share/postgresql/17/extension/age--1.6.0.sql /usr/share/postgresql/17/extension/age--1.6.0.sql
  COPY --from=apache/age:release_PG17_1.6.0 /usr/share/postgresql/17/extension/age.control /usr/share/postgresql/17/extension/age.control
  ```
- **shared_preload_libraries join** — replace the timescaledb-only `command:` in dev/test/prod/staging postgres services with a computed list so `timescaledb` + `age` (or either) are joined:
  ```jinja
  {%- set _preloads = [] %}
  {%- if "timescaledb" in batteries %}{% set _ = _preloads.append("timescaledb") %}{% endif %}
  {%- if "age" in batteries %}{% set _ = _preloads.append("age") %}{% endif %}
  {%- if _preloads %}
      command: ["postgres", "-c", "shared_preload_libraries={{ _preloads | join(',') }}"]
  {%- endif %}
  ```
  (and the conftest `with_command` likewise: `"postgres -c shared_preload_libraries=" + the joined list`, gated `{%- if "timescaledb" in batteries or "age" in batteries %}`.)
- **0006 migration** (`down_revision = "{{ down_revision_age }}"`): `op.execute("CREATE EXTENSION IF NOT EXISTS age")`; `op.execute("SELECT ag_catalog.create_graph('app_graph')")`. downgrade: `op.execute("SELECT ag_catalog.drop_graph('app_graph', true)")`. (Graph functions are available because `shared_preload_libraries=age` is set on the server alembic runs against; qualify `ag_catalog.create_graph`.)
- `migrations.py`: `MIGRATION_ORDER += ("age",)` (after timescaledb), `REVISIONS["age"]="0006"`.
- `batteries.py`: register `timescaledb` ("PostgreSQL TimescaleDB extension + a readings hypertable for time-series data") and `age` ("Apache AGE openCypher graph queries on Postgres (no new service)"), both `requires=()`.
- Render tests: `migration_down_revisions(["age"])=={"age":"0001"}`, `(["timescaledb","age"])=={"timescaledb":"0001","age":"0005"}`, `(["pgvector","timescaledb","age"])` chains 0004→0005→0006; render `["age"]` → Dockerfile has the AGE COPY, `shared_preload_libraries=age` in dev, `0006_graph.py` with `create_graph`; render `["timescaledb","age"]` → `shared_preload_libraries=timescaledb,age`; baseline `[]` byte-identical.
- TDD + fast gate + commit (`feat(db): age graph battery foundation — AGE multi-stage image, shared_preload join, 0006 create_graph migration, registration`).

## Task 5-AGE: AGE graph package + functional/acceptance tests

**Files:** new `src/{{package_name}}/{% if "age" in batteries %}graph{% endif %}/{__init__,repository}.py`, new `tests/functional/{{ 'test_graph.py' if 'age' in batteries else '' }}.jinja`, `tests/test_copier_runner.py` (render test), `tests/acceptance/test_rendered_project.py` (live acceptance).

- `graph/repository.py` — Cypher-in-SQL over the project's SQLAlchemy `Session` (no new dep, no bolt driver):
  ```python
  from sqlalchemy import text
  from sqlalchemy.orm import Session

  _GRAPH = "app_graph"


  def _prepare(session: Session) -> None:
      # AGE functions live in ag_catalog; make them resolvable for this session.
      session.execute(text('SET search_path = ag_catalog, "$user", public'))


  def relate(session: Session, src: str, dst: str, kind: str = "KNOWS") -> None:
      """Create two Person nodes (by name) and a typed relationship between them.

      ``src``/``dst``/``kind`` are interpolated into the Cypher text — AGE's cypher()
      cannot bind them as parameters — so pass only trusted, app-controlled values.
      """
      _prepare(session)
      session.execute(
          text(
              f"SELECT * FROM cypher('{_GRAPH}', $$ "
              f"MERGE (a:Person {{name: '{src}'}}) MERGE (b:Person {{name: '{dst}'}}) "
              f"MERGE (a)-[:{kind}]->(b) $$) AS (v agtype)"
          )
      )
      session.commit()


  def neighbors(session: Session, name: str) -> list[str]:
      """Names directly reachable from `name` by any outgoing relationship."""
      _prepare(session)
      rows = session.execute(
          text(
              f"SELECT * FROM cypher('{_GRAPH}', $$ "
              f"MATCH (a:Person {{name: '{name}'}})-->(b:Person) RETURN b.name $$) AS (name agtype)"
          )
      )
      # agtype string results come back JSON-quoted (e.g. '"beta"'); strip the quotes.
      return [str(r.name).strip('"') for r in rows]
  ```
  `graph/__init__.py` empty.
- `tests/functional/test_graph.py.jinja` (uses the `db_session` fixture — which builds the AGE custom image + runs `alembic upgrade head` including 0006):
  ```python
  from {{ package_name }}.graph.repository import neighbors, relate


  def test_relate_and_neighbors(db_session):
      relate(db_session, "alpha", "beta")
      assert "beta" in neighbors(db_session, "alpha")
  ```
- Render test: `["age"]` renders `graph/repository.py` + `test_graph.py`; baseline omits them.
- Acceptance test `test_rendered_age_battery_passes` (mirror the pgvector one): render `["age"]`, `uv sync`, `bash scripts/coverage.sh 70 unit functional` returncode 0 + `graph/repository.py` reaches 100% (proves the round-trip ran on the live AGE image). Run it, then `rm -rf /tmp/pytest-of-chris/* 2>/dev/null`.
- TDD + fast gate + commit (`feat(db): age graph battery — Cypher-in-SQL graph repo + functional test`).
