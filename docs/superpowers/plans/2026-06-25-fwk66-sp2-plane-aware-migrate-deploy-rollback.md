# FWK66 (SP2) — Plane-aware migrate / deploy / rollback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make schema migration, deploy, and rollback plane-aware for the `multitenantauth` battery — a control-first migrate fan-out across the control plane + the default business DB + every active tenant DB, plane-aware boot/Taskfile wiring, and image-only rollback (no schema downgrade on any plane) with contract migrations as an explicit rollback floor.

**Architecture:** A new locked `multitenantauth/tenancy/migrate.py` exposes `upgrade_all()` built on SP1's `migrate_tenant(dsn)` primitive (alembic via the Python API) + a new `active_tenant_dsns()` control-repo query. The entrypoint and a new `db:migrate:all` Taskfile target invoke it; `infra/deploy/strategy.sh` becomes a jinja template whose battery branch does image-only rollback gated by a new `scripts/rollback_guard.py` contract-floor check; `scripts/check_migrations.py` is extended to scan both alembic chains. Everything is gated on the battery — a render without `multitenantauth` behaves exactly as today.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x (sync), Alembic (Python API), FastAPI, Copier (jinja template payload), pytest, Postgres (testcontainer for the real-PG tier), bash (deploy/boot scripts).

## Global Constraints

Every task's requirements implicitly include this section. Values copied verbatim from the spec (`docs/superpowers/specs/2026-06-25-fwk66-sp2-plane-aware-migrate-deploy-rollback-design.md`).

- **Battery-gated, non-battery byte-identical.** Every change gates on `"multitenantauth" in batteries`. A render *without* the battery must behave exactly as today: `infra/deploy/strategy.sh` rollback stays `downgrade ${rev}` → redeploy; `db:migrate` unchanged; `scripts/entrypoint.sh` runs the bare `alembic upgrade head`; `check_migrations.py` app-chain behavior unchanged.
- **Integrity-lock (fail-safe).** `src/{package_name}/multitenantauth/tenancy/migrate.py` MUST be added to `BATTERY_LOCKED_SRC` in `src/framework_cli/integrity/classes.py` **in the same task that creates it** — the lock-completeness walk (`tests/integrity/test_auth_mechanism_lock.py`) fails the moment an unregistered mechanism file renders. The edit to the LOCKED `db/control/repository.py` is a deliberate mechanism re-touch (its checksum regenerates; covered by the branch-end Layer-2 review).
- **Never log a DSN or credential.** `upgrade_all`'s result-map values and all log lines use the exception **class name** only (`type(exc).__name__`) — never an exception message, never a DSN. Reuse SP1's never-log hygiene and the `migrate_tenant` `%%`-escape.
- **Alembic via the Python API** (`alembic.command.upgrade` + a programmatic `alembic.config.Config`), never a subprocess.
- **Ordering & failure policy:** control-first **fail-fast** (control failure aborts before any tenant is touched); the default business DB is recorded-not-aborting; the tenant fan-out is **best-effort** (continue past a failed tenant); `main()` exits non-zero if any target failed. **Sequential** — no parallelism.
- **Active-only:** the fan-out migrates `status == "active"` tenants only.
- **Rollback (battery):** **image-only — no `alembic downgrade` on any plane.** A `# deploy: contract` migration is a rollback floor; `scripts/rollback_guard.py` refuses to cross one (override: `ALLOW_CONTRACT_ROLLBACK=1`, for an operator who has a data-restore plan).
- **Template-payload TDD loop** (`[[template-payload-tdd-loop]]`): template tests run in a *generated* project. render → `uv sync` → edit framework source → mirror (`cp` the `.py`; render+`cp` the `.jinja`) → `pytest` in the work dir; `ruff format --check` the rendered output. Set `TMPDIR=/var/tmp` for renders/acceptance.
- **Test tiers (directory-based, no markers):** pure-unit → `tests/unit/`; real-Postgres → `tests/functional/` (uses the SP1 fixtures `ctrl_engine`, `control_db_url`, `drop_tenant_db`, `truncate_control`). The real-Postgres tier is **never skip-neutral** — it must run in CI's Postgres tier, not degrade to a silent pass.
- **Canonical render package name is `demo`** (asserts in framework-level tests use `demo`).
- **Quality gate green before every commit:** `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`.

## File Structure

**Template payload (rendered into generated projects):**
- `src/{{package_name}}/{…multitenantauth…}/tenancy/migrate.py` — **CREATE** (locked). `upgrade_all()` + `main()` + the result-map helpers. The plane-aware fan-out.
- `src/{{package_name}}/db/{…control…}/repository.py` — **MODIFY** (locked). Add `active_tenant_dsns()`.
- `scripts/entrypoint.sh.jinja` — **MODIFY**. Battery branch invokes the migrate runner.
- `Taskfile.yml.jinja` — **MODIFY**. Battery-gated `db:migrate:all`.
- `scripts/check_migrations.py` — **MODIFY**. Scan both chains; `main(dirs=None)`.
- `scripts/{{ 'rollback_guard.py' if 'multitenantauth' in batteries else '' }}` — **CREATE** (battery-only render). Contract-floor guard.
- `infra/deploy/strategy.sh` → `infra/deploy/strategy.sh.jinja` — **RENAME + MODIFY**. Battery branch = image-only rollback + guard; non-battery branch = today's body verbatim.
- `infra/deploy/README.md` — **MODIFY**. Plane-aware deploy/rollback + multi-host pre-roll section.

**Framework source:**
- `src/framework_cli/integrity/classes.py` — **MODIFY**. Register `migrate.py` in `BATTERY_LOCKED_SRC`.

**Tests (template payload, battery-gated paths):**
- `tests/unit/{{ 'test_migrate_fanout.py' if 'multitenantauth' in batteries else '' }}.jinja` — **CREATE** (unit, no PG).
- `tests/functional/{{ 'test_active_tenant_dsns.py' if 'multitenantauth' in batteries else '' }}.jinja` — **CREATE** (real PG).
- `tests/functional/{{ 'test_migrate_fanout_acceptance.py' if 'multitenantauth' in batteries else '' }}.jinja` — **CREATE** (real PG).
- `tests/functional/{{ 'test_rollback_guard.py' if 'multitenantauth' in batteries else '' }}.jinja` — **CREATE** (real PG, alembic walk).
- `tests/unit/{{ 'test_rollback_guard_decision.py' if 'multitenantauth' in batteries else '' }}.jinja` — **CREATE** (unit, no PG).

**Tests (framework-level, run in the framework venv):**
- `tests/test_check_migrations.py` — **CREATE** (loads the template script via importlib).
- Render-content assertions for entrypoint / Taskfile / strategy.sh added to `tests/test_copier_runner.py` (or a focused new module `tests/test_sp2_plane_aware_render.py`).

---

### Task 1: `active_tenant_dsns` control-repo enumeration

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/db/{% if "multitenantauth" in batteries %}control{% endif %}/repository.py` (after `get_tenant_dsn`, line 43) — LOCKED file, deliberate re-touch.
- Test: `src/framework_cli/template/tests/functional/{{ 'test_active_tenant_dsns.py' if 'multitenantauth' in batteries else '' }}.jinja` (CREATE)

**Interfaces:**
- Consumes: `Tenant` model (`.id`, `.dsn`, `.status`) already imported in `repository.py`; the SP1 fixtures `ctrl_engine`, `truncate_control` from `tests/conftest.py.jinja`.
- Produces: `active_tenant_dsns(session: Session) -> list[tuple[str, str]]` — `(tenant_id, dsn)` for every `status == "active"` tenant. Consumed by Task 2's `upgrade_all`.

- [ ] **Step 1: Write the failing test** (render → mirror → run in the generated project per the TDD loop)

Create `tests/functional/{{ 'test_active_tenant_dsns.py' if 'multitenantauth' in batteries else '' }}.jinja`:

```python
"""active_tenant_dsns returns exactly the active tenants' (id, dsn) — the migrate fan-out target set."""

from sqlalchemy.orm import Session

from {{ package_name }}.db.control import repository as control_repo


def _add(cs: Session, *, id: str, slug: str, status: str) -> None:
    control_repo.add_tenant(
        cs, id=id, name=id.title(), slug=slug,
        dsn=f"postgresql+psycopg://app:app@db:5432/{{ package_name }}_tenant_{id}",
        status=status,
    )


def test_active_tenant_dsns_returns_only_active(ctrl_engine, truncate_control):
    truncate_control()
    with Session(ctrl_engine) as cs:
        _add(cs, id="acme", slug="acme", status="active")
        _add(cs, id="globex", slug="globex", status="active")
        _add(cs, id="initech", slug="initech", status="provisioning")
        _add(cs, id="hooli", slug="hooli", status="suspended")
        cs.commit()

        result = control_repo.active_tenant_dsns(cs)

    ids = {tid for tid, _ in result}
    assert ids == {"acme", "globex"}
    assert all(dsn.endswith(f"{{ package_name }}_tenant_{tid}") for tid, dsn in result)
```

- [ ] **Step 2: Run test to verify it fails**

In the work dir: `uv run pytest tests/functional/test_active_tenant_dsns.py -v`
Expected: FAIL — `AttributeError: module 'demo.db.control.repository' has no attribute 'active_tenant_dsns'`.

- [ ] **Step 3: Write minimal implementation**

In `repository.py`, immediately after `get_tenant_dsn` (line 43), add:

```python
def active_tenant_dsns(session: Session) -> list[tuple[str, str]]:
    """Return (tenant_id, dsn) for every active tenant — the migrate fan-out target set.

    Active-only by design: a ``provisioning`` tenant has no committed schema contract yet,
    and ``suspended`` is an SP3 lifecycle concern. Returns the stored control-row DSN — this
    is an operator/boot path, not a request path, so it deliberately does NOT go through the
    request-scoped ``resolve_dsn`` seam.
    """
    rows = session.execute(
        select(Tenant.id, Tenant.dsn).where(Tenant.status == "active")
    ).all()
    return [(row.id, row.dsn) for row in rows]
```

(`select` and `Session` are already imported at the top of `repository.py`.)

- [ ] **Step 4: Run test to verify it passes**

`uv run pytest tests/functional/test_active_tenant_dsns.py -v`
Expected: PASS.

- [ ] **Step 5: Re-render + integrity check (locked-file re-touch)**

The edit changes a `BATTERY_LOCKED_SRC` file. Re-render and confirm integrity re-checksums cleanly (no stale lock): `framework integrity --ci` on a fresh `--with multitenantauth` render → OK.

- [ ] **Step 6: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/db/{% if \"multitenantauth\" in batteries %}control{% endif %}/repository.py" "src/framework_cli/template/tests/functional/{{ 'test_active_tenant_dsns.py' if 'multitenantauth' in batteries else '' }}.jinja"
git commit -m "feat(FWK66): active_tenant_dsns control-repo enumeration (fan-out target set)"
```

---

### Task 2: `upgrade_all()` fan-out runner + integrity-lock registration

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "multitenantauth" in batteries %}multitenantauth{% endif %}/tenancy/migrate.py`
- Modify: `src/framework_cli/integrity/classes.py` (after line 184, the `session.py` entry)
- Test: `src/framework_cli/template/tests/unit/{{ 'test_migrate_fanout.py' if 'multitenantauth' in batteries else '' }}.jinja` (CREATE)

**Interfaces:**
- Consumes: `active_tenant_dsns` (Task 1); `migrate_tenant(dsn)` from `tenancy/provision.py`; `control_session_factory()` from `db.control.engine`; `alembic.command.upgrade`, `alembic.config.Config`.
- Produces:
  - `upgrade_all() -> dict[str, object]` — `{"control": "ok"|<errclass>, "default": "ok"|<errclass>|None, "tenants": {tenant_id: "ok"|<errclass>}}`.
  - `report_failed(report: dict) -> list[str]` — the failed target labels.
  - `main() -> int` — runs `upgrade_all`, prints the report as JSON, returns non-zero on any failure. Invoked as `python -m {package}.multitenantauth.tenancy.migrate`.
  - Module-level seams (monkeypatchable in tests): `_upgrade_control`, `_upgrade_default`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/{{ 'test_migrate_fanout.py' if 'multitenantauth' in batteries else '' }}.jinja`:

```python
"""Plane-aware fan-out: ordering, control-fail-fast, tenant best-effort, no-DSN-in-report (unit, no PG)."""

import contextlib

import pytest

from {{ package_name }}.multitenantauth.tenancy import migrate


@pytest.fixture
def patched(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(migrate, "_upgrade_control", lambda: calls.append("control"))
    monkeypatch.setattr(migrate, "_upgrade_default", lambda: calls.append("default"))
    monkeypatch.setattr(migrate, "migrate_tenant", lambda dsn: calls.append(f"tenant:{dsn}"))
    monkeypatch.setattr(migrate, "control_session_factory", lambda: (lambda: contextlib.nullcontext(object())))
    monkeypatch.setattr(migrate, "active_tenant_dsns", lambda cs: [("acme", "dsn-a"), ("globex", "dsn-b")])
    return calls


def test_order_is_control_then_default_then_tenants(patched):
    report = migrate.upgrade_all()
    assert patched == ["control", "default", "tenant:dsn-a", "tenant:dsn-b"]
    assert report["control"] == "ok"
    assert report["default"] == "ok"
    assert report["tenants"] == {"acme": "ok", "globex": "ok"}
    assert migrate.report_failed(report) == []


def test_control_failure_aborts_before_any_tenant(patched, monkeypatch):
    def boom():
        raise RuntimeError("control down")

    monkeypatch.setattr(migrate, "_upgrade_control", boom)
    report = migrate.upgrade_all()
    assert patched == []  # no default, no tenant touched
    assert report["control"] == "RuntimeError"
    assert report["default"] is None
    assert report["tenants"] == {}
    assert migrate.report_failed(report) == ["control"]


def test_tenant_failure_is_best_effort(patched, monkeypatch):
    def one_bad(dsn):
        if dsn == "dsn-a":
            raise ConnectionError("nope")
        patched.append(f"tenant:{dsn}")

    monkeypatch.setattr(migrate, "migrate_tenant", one_bad)
    report = migrate.upgrade_all()
    assert "tenant:dsn-b" in patched  # globex still attempted after acme failed
    assert report["tenants"] == {"acme": "ConnectionError", "globex": "ok"}
    assert migrate.report_failed(report) == ["acme"]


def test_report_never_contains_dsn_or_message(patched, monkeypatch):
    secret = "postgresql+psycopg://u:SECRET@h/db"

    def leaky(dsn):
        raise ValueError(secret)

    monkeypatch.setattr(migrate, "migrate_tenant", leaky)
    report = migrate.upgrade_all()
    assert report["tenants"]["acme"] == "ValueError"
    assert "SECRET" not in repr(report)


def test_main_exit_codes(patched, monkeypatch):
    assert migrate.main() == 0
    monkeypatch.setattr(migrate, "_upgrade_control", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert migrate.main() == 1
```

- [ ] **Step 2: Run test to verify it fails**

`uv run pytest tests/unit/test_migrate_fanout.py -v`
Expected: FAIL — `ModuleNotFoundError: ... tenancy.migrate`.

- [ ] **Step 3: Write minimal implementation**

Create `tenancy/migrate.py`:

```python
"""Plane-aware migration fan-out (Phase 2 / SP2).

upgrade_all: migrate the control plane (fail-fast), then the default business DB, then every
ACTIVE tenant DB (best-effort) — built on SP1's per-tenant migrate primitive. A single
`alembic upgrade head` migrates only one plane; this reaches all three. Returns a per-target
result map; values are exception CLASS names only (never a DSN/credential). Sequential and
idempotent (every step is `upgrade head`).

Invoked at boot / pre-roll: `python -m {{ package_name }}.multitenantauth.tenancy.migrate`.
This file is integrity-LOCKED mechanism."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from ...db.control import repository as control_repo
from ...db.control.engine import control_session_factory
from .provision import migrate_tenant

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    # src/<pkg>/multitenantauth/tenancy/migrate.py → project root is parents[4].
    return Path(__file__).resolve().parents[4]


def _upgrade_control() -> None:
    """Upgrade the CONTROL chain to head. control env.py always points at control_database_url,
    so no url injection is needed here."""
    command.upgrade(Config(str(_project_root() / "alembic_control.ini")), "head")


def _upgrade_default() -> None:
    """Upgrade the APP chain to head against the default business DB. app env.py falls back to
    database_url when no sqlalchemy.url is injected, so a plain upgrade targets the default DB."""
    command.upgrade(Config(str(_project_root() / "alembic.ini")), "head")


def upgrade_all() -> dict[str, object]:
    """Control-first → default DB → active-tenant fan-out. See module docstring."""
    report: dict[str, object] = {"control": None, "default": None, "tenants": {}}

    # Control plane FIRST, fail-fast: the registry that enumerates tenants lives here.
    try:
        _upgrade_control()
        report["control"] = "ok"
    except Exception as exc:  # noqa: BLE001 — record class name, abort, never leak the message
        report["control"] = type(exc).__name__
        logger.error("migrate.control.failed error=%s", type(exc).__name__)
        return report  # do NOT touch any tenant on a broken control plane

    # Default business DB (independent of tenants — record, do not abort the fan-out).
    try:
        _upgrade_default()
        report["default"] = "ok"
    except Exception as exc:  # noqa: BLE001
        report["default"] = type(exc).__name__
        logger.error("migrate.default.failed error=%s", type(exc).__name__)

    # Tenant fan-out, best-effort.
    with control_session_factory()() as cs:
        targets = control_repo.active_tenant_dsns(cs)
    tenants: dict[str, str] = {}
    for tenant_id, dsn in targets:
        try:
            migrate_tenant(dsn)
            tenants[tenant_id] = "ok"
        except Exception as exc:  # noqa: BLE001
            tenants[tenant_id] = type(exc).__name__
            logger.warning("migrate.tenant.failed tenant_id=%s error=%s", tenant_id, type(exc).__name__)
    report["tenants"] = tenants
    return report


def report_failed(report: dict[str, object]) -> list[str]:
    """Target labels that did not migrate (control/default that ran-and-failed, or any tenant).
    A None default means control aborted before the default was reached — already a failure."""
    failed: list[str] = []
    if report["control"] != "ok":
        failed.append("control")
    if report["default"] not in ("ok", None):
        failed.append("default")
    failed.extend(t for t, v in report["tenants"].items() if v != "ok")  # type: ignore[union-attr]
    return failed


def main() -> int:
    report = upgrade_all()
    print(json.dumps(report))
    failed = report_failed(report)
    if failed:
        print(f"migrate failed for: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`active_tenant_dsns` is referenced as `control_repo.active_tenant_dsns` so the unit test's `monkeypatch.setattr(migrate, "active_tenant_dsns", ...)` patches the module-level name — therefore also bind it at import for patchability:

```python
from ...db.control.repository import active_tenant_dsns  # noqa: F401 — module-level for monkeypatch
```

and call `active_tenant_dsns(cs)` (not `control_repo.active_tenant_dsns(cs)`) inside `upgrade_all`.

- [ ] **Step 4: Register the lock (same task — fail-safe)**

In `src/framework_cli/integrity/classes.py`, after line 184 (`"src/{package_name}/multitenantauth/tenancy/session.py": ("multitenantauth",),`) add:

```python
    "src/{package_name}/multitenantauth/tenancy/migrate.py": ("multitenantauth",),
```

- [ ] **Step 5: Run tests to verify they pass**

`uv run pytest tests/unit/test_migrate_fanout.py -v` → PASS.
Framework integrity-lock completeness: re-render `--with multitenantauth`, `framework integrity --ci` → OK (migrate.py now locked); tamper `migrate.py` → exit 1.

- [ ] **Step 6: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/.../tenancy/migrate.py" src/framework_cli/integrity/classes.py "src/framework_cli/template/tests/unit/.../test_migrate_fanout.py.jinja"
git commit -m "feat(FWK66): upgrade_all plane-aware migrate fan-out (control-first, best-effort tenants) + integrity lock"
```

---

### Task 3: Real-Postgres fan-out + isolation + broken-tenant acceptance

**Files:**
- Test: `src/framework_cli/template/tests/functional/{{ 'test_migrate_fanout_acceptance.py' if 'multitenantauth' in batteries else '' }}.jinja` (CREATE)

**Interfaces:**
- Consumes: `upgrade_all`, `report_failed` (Task 2); `provision_tenant` (`tenancy/provision.py`); `tenant_session`, `invalidate_dsn_cache` (`tenancy/session.py`); `default_tenant_dsn` (`tenancy/dsn.py`); SP1 fixtures `ctrl_engine`, `control_db_url`, `drop_tenant_db`, `truncate_control`.
- Produces: nothing (acceptance only). This is the never-skip-neutral real-PG conformance gate.

- [ ] **Step 1: Write the failing test** (mirror `test_tenant_provisioning.py` patterns)

Create `tests/functional/{{ 'test_migrate_fanout_acceptance.py' if 'multitenantauth' in batteries else '' }}.jinja`:

```python
"""SP2 conformance (real Postgres): upgrade_all reaches control + default + every tenant DB,
isolation holds, and a broken tenant is flagged best-effort. Never skip-neutral."""

import pytest
from sqlalchemy import inspect, make_url, text
from sqlalchemy.orm import Session

from {{ package_name }}.config.settings import get_settings
from {{ package_name }}.db.control import repository as control_repo
from {{ package_name }}.multitenantauth.tenancy.dsn import default_tenant_dsn
from {{ package_name }}.multitenantauth.tenancy.engine_registry import reset_tenant_engines
from {{ package_name }}.multitenantauth.tenancy.migrate import report_failed, upgrade_all
from {{ package_name }}.multitenantauth.tenancy.provision import provision_tenant
from {{ package_name }}.multitenantauth.tenancy.session import invalidate_dsn_cache, tenant_session


@pytest.fixture(autouse=True)
def _env(monkeypatch, control_db_url, engine):
    # Control on the dedicated ctrl DB; default business DB = the testcontainer DB.
    monkeypatch.setenv("APP_CONTROL_DATABASE_URL", control_db_url)
    monkeypatch.setenv("APP_DATABASE_URL", str(engine.url.render_as_string(hide_password=False)))
    monkeypatch.setenv("APP_TENANT_DB_NAME_PREFIX", "{{ package_name }}_fanout")
    get_settings.cache_clear()
    invalidate_dsn_cache()
    reset_tenant_engines()
    yield
    get_settings.cache_clear()
    invalidate_dsn_cache()
    reset_tenant_engines()


def test_upgrade_all_reaches_every_plane_and_is_isolated(ctrl_engine, truncate_control, drop_tenant_db):
    truncate_control()
    dbs = []
    try:
        with Session(ctrl_engine) as cs:
            acme = provision_tenant(cs, "Acme", slug="acme")
            globex = provision_tenant(cs, "Globex", slug="globex")
            cs.commit()
        dbs = [make_url(default_tenant_dsn(t)).database for t in (acme, globex)]

        report = upgrade_all()
        assert report["control"] == "ok"
        assert report["default"] == "ok"
        assert report["tenants"] == {acme: "ok", globex: "ok"}
        assert report_failed(report) == []

        # Every tenant DB has the business schema; isolation holds.
        invalidate_dsn_cache()
        with Session(ctrl_engine) as cs:
            with tenant_session(acme, control_session=cs) as ts:
                assert "items" in inspect(ts.bind).get_table_names()
                ts.execute(text("INSERT INTO items (name) VALUES ('acme-only')"))
                ts.commit()
            with tenant_session(globex, control_session=cs) as ts:
                names = [r[0] for r in ts.execute(text("SELECT name FROM items"))]
                assert "acme-only" not in names  # A's write invisible to B
    finally:
        reset_tenant_engines()
        for db in dbs:
            drop_tenant_db(db)


def test_broken_tenant_is_flagged_others_still_migrate(ctrl_engine, truncate_control, drop_tenant_db):
    truncate_control()
    dbs = []
    try:
        with Session(ctrl_engine) as cs:
            acme = provision_tenant(cs, "Acme", slug="acme")
            cs.commit()
            # Inject an ACTIVE tenant whose DSN points nowhere (no physical DB).
            control_repo.add_tenant(
                cs, id="ghost", name="Ghost", slug="ghost",
                dsn="postgresql+psycopg://app:app@127.0.0.1:5599/{{ package_name }}_fanout_ghost",
                status="active",
            )
            cs.commit()
        dbs = [make_url(default_tenant_dsn(acme)).database]

        report = upgrade_all()
        assert report["control"] == "ok"
        assert report["tenants"][acme] == "ok"
        assert report["tenants"]["ghost"] != "ok"  # connection failure, flagged
        assert "ghost" in report_failed(report)
    finally:
        reset_tenant_engines()
        for db in dbs:
            drop_tenant_db(db)
```

(If the engine-registry reset helper is named differently than `reset_tenant_engines`, use the name SP1's `test_tenant_provisioning.py` uses — verify against `tenancy/engine_registry.py` while implementing.)

- [ ] **Step 2: Run test to verify it fails**

`TMPDIR=/var/tmp uv run pytest tests/functional/test_migrate_fanout_acceptance.py -v`
Expected: FAIL initially only if Task 2 wiring is incomplete; otherwise this is a regression guard. If it passes immediately, confirm by temporarily breaking `_upgrade_default` to see the assertion bite, then revert.

- [ ] **Step 3: Implementation**

No new implementation — this exercises Tasks 1–2. If a real-PG behavior surfaces (e.g., `upgrade_all` doesn't read the monkeypatched settings because of caching), the minimal fix lands here (e.g., ensure `_upgrade_control`/`_upgrade_default` don't capture a stale config).

- [ ] **Step 4: Run test to verify it passes**

`TMPDIR=/var/tmp uv run pytest tests/functional/test_migrate_fanout_acceptance.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add "src/framework_cli/template/tests/functional/.../test_migrate_fanout_acceptance.py.jinja"
git commit -m "test(FWK66): real-PG fan-out + isolation + broken-tenant acceptance (never skip-neutral)"
```

---

### Task 4: Plane-aware container entrypoint

**Files:**
- Modify: `src/framework_cli/template/scripts/entrypoint.sh.jinja`
- Test: render-content assertions in `tests/test_copier_runner.py` (or `tests/test_sp2_plane_aware_render.py`, CREATE)

**Interfaces:**
- Consumes: `upgrade_all` via `python -m {package}.multitenantauth.tenancy.migrate` (Task 2).
- Produces: an entrypoint whose battery branch runs the plane-aware fan-out instead of two bare `alembic upgrade head` lines.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py` (uses the module-level `DATA` + `render_project`):

```python
def test_entrypoint_plane_aware_under_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["multitenantauth"]})
    text = (dest / "scripts" / "entrypoint.sh").read_text()
    assert "python -m demo.multitenantauth.tenancy.migrate" in text
    assert "demo.multitenantauth.authz.seed" in text          # authz seed preserved
    # The plane-blind bare app-chain upgrade must NOT be in the battery branch.
    assert "alembic -c alembic_control.ini upgrade head" not in text


def test_entrypoint_unchanged_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)  # no batteries
    text = (dest / "scripts" / "entrypoint.sh").read_text()
    assert "alembic upgrade head" in text
    assert "tenancy.migrate" not in text
```

- [ ] **Step 2: Run test to verify it fails**

`uv run pytest tests/test_copier_runner.py::test_entrypoint_plane_aware_under_battery -v`
Expected: FAIL — `python -m demo.multitenantauth.tenancy.migrate` not present.

- [ ] **Step 3: Edit `scripts/entrypoint.sh.jinja`**

Replace the migration block (current lines 9–18) with:

```bash
if [ "${APP_RUN_MIGRATIONS:-true}" = "true" ]; then
{%- if "multitenantauth" in batteries %}
  # Plane-aware migrate: the control plane FIRST, then the default business DB, then a fan-out
  # over every active tenant DB. A single `alembic upgrade head` would migrate only ONE plane and
  # silently leave the tenant DBs stale. Multi-host roll: set APP_RUN_MIGRATIONS=false on the app
  # hosts and run `task db:migrate:all` once before the roll (see infra/deploy/README.md).
  python -m {{ package_name }}.multitenantauth.tenancy.migrate
  # Seed the control vocabulary (permissions/roles) BEFORE the consumer seed, so any consumer
  # data that depends on the authz vocabulary always finds it present.
  python -m {{ package_name }}.multitenantauth.authz.seed
{%- else %}
  alembic upgrade head
{%- endif %}
  python scripts/seed.py
fi
exec "$@"
```

- [ ] **Step 4: Run tests to verify they pass**

`uv run pytest tests/test_copier_runner.py -k entrypoint -v` → PASS (both).
Sanity: render both ways and `bash -n` the rendered `scripts/entrypoint.sh` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/scripts/entrypoint.sh.jinja tests/test_copier_runner.py
git commit -m "feat(FWK66): plane-aware container entrypoint (battery runs the migrate fan-out)"
```

---

### Task 5: `db:migrate:all` Taskfile target

**Files:**
- Modify: `src/framework_cli/template/Taskfile.yml.jinja` (after `db:seed`, lines 160–163)
- Test: render-content assertions in `tests/test_copier_runner.py`

**Interfaces:**
- Consumes: `upgrade_all` via the module entry (Task 2).
- Produces: an operator-facing `task db:migrate:all` (the multi-host pre-roll handle), battery-gated. Bare `db:migrate` unchanged.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_taskfile_db_migrate_all_under_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["multitenantauth"]})
    text = (dest / "Taskfile.yml").read_text()
    assert "db:migrate:all:" in text
    assert "python -m demo.multitenantauth.tenancy.migrate" in text
    assert "uv run alembic upgrade head" in text  # bare db:migrate still present


def test_taskfile_no_db_migrate_all_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    text = (dest / "Taskfile.yml").read_text()
    assert "db:migrate:all:" not in text
    assert "db:migrate:" in text  # the single-DB target is unchanged
```

- [ ] **Step 2: Run test to verify it fails**

`uv run pytest tests/test_copier_runner.py::test_taskfile_db_migrate_all_under_battery -v`
Expected: FAIL — `db:migrate:all:` absent.

- [ ] **Step 3: Edit `Taskfile.yml.jinja`**

After the `db:seed:` target (line 163, before the `{% if "workers" in batteries %}` block) insert:

```yaml
{%- if "multitenantauth" in batteries %}

  db:migrate:all:
    desc: Plane-aware migration fan-out — the control plane, the default DB, then every active tenant DB. Run this ONCE before a multi-host roll (with APP_RUN_MIGRATIONS=false on the app hosts); see infra/deploy/README.md.
    cmds:
      - uv run python -m {{ package_name }}.multitenantauth.tenancy.migrate
{%- endif %}
```

- [ ] **Step 4: Run tests to verify they pass**

`uv run pytest tests/test_copier_runner.py -k taskfile -v` → PASS.
Sanity: render `--with multitenantauth`, `uv run task --list` in the work dir shows `db:migrate:all` (YAML valid).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(FWK66): db:migrate:all Taskfile target (battery-gated multi-host pre-roll)"
```

---

### Task 6: `check_migrations.py` scans both chains

**Files:**
- Modify: `src/framework_cli/template/scripts/check_migrations.py`
- Test: `tests/test_check_migrations.py` (CREATE, framework-level — loads the template script via importlib)

**Interfaces:**
- Consumes: nothing new (stdlib `ast`).
- Produces: `main(dirs: list[Path] | None = None) -> int` scanning `migrations/versions` **and** `migrations_control/versions` (each only if present). The contract marker (`# deploy: contract`) is now authoritative in the control chain too — needed by Task 7's rollback floor.

- [ ] **Step 1: Write the failing test**

Create `tests/test_check_migrations.py`:

```python
"""check_migrations scans BOTH alembic chains (app + control). Framework-level: loads the
template script via importlib and exercises it with temp migration dirs."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src/framework_cli/template/scripts/check_migrations.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("check_migrations", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_GOOD = "def upgrade():\n    op.add_column('t', c)\n\n\ndef downgrade():\n    op.drop_column('t', 'c')\n"
_BAD = "def upgrade():\n    op.drop_table('t')\n\n\ndef downgrade():\n    op.create_table('t')\n"
_BAD_MARKED = "# deploy: contract\n" + _BAD


def _write(d: Path, name: str, body: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body)


def test_clean_app_chain_passes(tmp_path):
    mod = _load()
    _write(tmp_path / "app", "0001.py", _GOOD)
    assert mod.main([tmp_path / "app"]) == 0


def test_destructive_unmarked_control_migration_fails(tmp_path):
    mod = _load()
    _write(tmp_path / "app", "0001.py", _GOOD)
    _write(tmp_path / "control", "c0001.py", _BAD)
    assert mod.main([tmp_path / "app", tmp_path / "control"]) == 1


def test_contract_marked_control_migration_passes(tmp_path):
    mod = _load()
    _write(tmp_path / "control", "c0001.py", _BAD_MARKED)
    assert mod.main([tmp_path / "control"]) == 0


def test_absent_dir_is_skipped(tmp_path):
    mod = _load()
    _write(tmp_path / "app", "0001.py", _GOOD)
    assert mod.main([tmp_path / "app", tmp_path / "does_not_exist"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

`uv run pytest tests/test_check_migrations.py -v`
Expected: FAIL — `main()` takes no `dirs` argument / control chain not scanned.

- [ ] **Step 3: Edit `scripts/check_migrations.py`**

Add the control versions path constant (after line 27):

```python
VERSIONS = Path("migrations/versions")
CONTROL_VERSIONS = Path("migrations_control/versions")
```

Replace `main()` (lines 106–122) with a dirs-parameterized version:

```python
def main(dirs: list[Path] | None = None) -> int:
    scan = dirs if dirs is not None else [VERSIONS, CONTROL_VERSIONS]
    failures = [
        msg
        for d in scan
        if d.is_dir()
        for path in sorted(d.glob("*.py"))
        for msg in _problems(path)
    ]
    for msg in failures:
        print(f"::error::{msg}", file=sys.stderr)
    if failures:
        print(
            f"\n{len(failures)} unsafe migration(s). Migrations must be reversible AND "
            "backward-compatible (expand-only); never destroy unreconstructable data. "
            "See infra/deploy/README.md.",
            file=sys.stderr,
        )
        return 1
    return 0
```

(The early `if not VERSIONS.is_dir(): return 0` guard is removed — the per-dir `if d.is_dir()` handles a missing dir; an app-only project still passes.)

- [ ] **Step 4: Run tests to verify they pass**

`uv run pytest tests/test_check_migrations.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/scripts/check_migrations.py tests/test_check_migrations.py
git commit -m "feat(FWK66): check_migrations scans both alembic chains (control contract marker authoritative)"
```

---

### Task 7: `rollback_guard.py` contract-floor

**Files:**
- Create: `src/framework_cli/template/scripts/{{ 'rollback_guard.py' if 'multitenantauth' in batteries else '' }}` (battery-only render; no jinja vars inside → no `.jinja` suffix)
- Test (unit, no PG): `tests/unit/{{ 'test_rollback_guard_decision.py' if 'multitenantauth' in batteries else '' }}.jinja` (CREATE)
- Test (real alembic walk): `tests/functional/{{ 'test_rollback_guard.py' if 'multitenantauth' in batteries else '' }}.jinja` (CREATE)

**Interfaces:**
- Consumes: `alembic.config.Config`, `alembic.script.ScriptDirectory`; the rendered project's `alembic.ini` / `alembic_control.ini`.
- Produces: a CLI `python scripts/rollback_guard.py <app_target_revision>` — exit 0 (rollback safe / overridden), 1 (refused: crosses a contract migration), 2 (usage). Functions: `_has_marker(path)`, `_app_contract_in_range(target_rev)`, `_control_contract_any()`, `main(argv=None)`. Consumed by Task 8's `strategy.sh` battery rollback.

- [ ] **Step 1: Write the failing unit test (decision + override logic)**

Create `tests/unit/{{ 'test_rollback_guard_decision.py' if 'multitenantauth' in batteries else '' }}.jinja`:

```python
"""rollback_guard decision logic (unit, no alembic walk — the walk functions are patched)."""

import importlib.util
from pathlib import Path

import pytest

_GUARD = Path("scripts/rollback_guard.py")


def _load():
    spec = importlib.util.spec_from_file_location("rollback_guard", _GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def guard(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_app_contract_in_range", lambda rev: [])
    monkeypatch.setattr(mod, "_control_contract_any", lambda: [])
    return mod


def test_usage_error_without_target(guard):
    assert guard.main([]) == 2


def test_clean_rollback_allowed(guard):
    assert guard.main(["abc123"]) == 0


def test_app_contract_in_range_refuses(guard, monkeypatch):
    monkeypatch.setattr(guard, "_app_contract_in_range", lambda rev: ["0007_drop.py"])
    assert guard.main(["abc123"]) == 1


def test_control_contract_refuses(guard, monkeypatch):
    monkeypatch.setattr(guard, "_control_contract_any", lambda: ["c0004_drop.py"])
    assert guard.main(["abc123"]) == 1


def test_override_allows_with_warning(guard, monkeypatch):
    monkeypatch.setattr(guard, "_app_contract_in_range", lambda rev: ["0007_drop.py"])
    monkeypatch.setenv("ALLOW_CONTRACT_ROLLBACK", "1")
    assert guard.main(["abc123"]) == 0


def test_marker_detection(guard, tmp_path):
    f = tmp_path / "m.py"
    f.write_text("# deploy: contract\ndef upgrade(): ...\n")
    assert guard._has_marker(f) is True
    f.write_text("def upgrade(): ...\n")
    assert guard._has_marker(f) is False
```

(The unit test runs in the rendered project; cwd is the project root so `scripts/rollback_guard.py` resolves. Render `--with multitenantauth`.)

- [ ] **Step 2: Run test to verify it fails**

`uv run pytest tests/unit/test_rollback_guard_decision.py -v` → FAIL (file missing).

- [ ] **Step 3: Create `scripts/{{ 'rollback_guard.py' if 'multitenantauth' in batteries else '' }}`**

```python
"""Refuse an image-only rollback that would cross a contract (destructive) migration.

Under multitenantauth, deploy rollback is image-only (no `alembic downgrade` on ANY plane) —
safe ONLY within an expand-only window. A `# deploy: contract` migration is a rollback floor:
the prior image needs schema the contract dropped, so crossing it requires a manual data-restore
plan, not an automated rollback. Refuse (exit 1) if the app chain's (target, head] range contains
a contract migration, OR if the control chain contains ANY contract migration (the control rev is
not tracked per-release, so it is treated as always-in-range — the most sensitive plane; a future
enhancement tracks the control rev per release for a precise control floor). Operator override
(with a data-restore plan): ALLOW_CONTRACT_ROLLBACK=1.

Usage: python scripts/rollback_guard.py <app_target_revision>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_CONTRACT_MARKER = "deploy: contract"


def _has_marker(path: Path) -> bool:
    return _CONTRACT_MARKER in path.read_text()


def _app_contract_in_range(target_rev: str) -> list[str]:
    """Contract-marked app revisions strictly newer than target_rev up to head. Fail-closed:
    if the range can't be resolved, treat as unsafe (caller refuses)."""
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    offenders: list[str] = []
    for rev in script.walk_revisions(target_rev, "heads"):
        if rev.revision == target_rev:
            continue  # exclusive lower bound — the target itself is where we roll back TO
        if _has_marker(Path(rev.path)):
            offenders.append(Path(rev.path).name)
    return offenders


def _control_contract_any() -> list[str]:
    """Any contract-marked control revision (control rev untracked per-release → always-in-range)."""
    cfg_path = Path("alembic_control.ini")
    if not cfg_path.exists():
        return []
    script = ScriptDirectory.from_config(Config(str(cfg_path)))
    return [
        Path(rev.path).name
        for rev in script.walk_revisions("base", "heads")
        if _has_marker(Path(rev.path))
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: rollback_guard.py <app_target_revision>", file=sys.stderr)
        return 2
    target = args[0]
    try:
        offenders = _app_contract_in_range(target) + _control_contract_any()
    except Exception as exc:  # noqa: BLE001 — cannot prove the range safe → refuse (fail-closed)
        print(
            f"::error::rollback guard could not resolve the migration range "
            f"({type(exc).__name__}); refusing image-only rollback. Override: ALLOW_CONTRACT_ROLLBACK=1.",
            file=sys.stderr,
        )
        return 0 if os.environ.get("ALLOW_CONTRACT_ROLLBACK") == "1" else 1
    if offenders:
        if os.environ.get("ALLOW_CONTRACT_ROLLBACK") == "1":
            print(
                f"::warning::rollback crosses contract migration(s) {offenders}; "
                "ALLOW_CONTRACT_ROLLBACK=1 set — proceeding (ensure a data-restore plan).",
                file=sys.stderr,
            )
            return 0
        print(
            f"::error::image-only rollback refused — crosses contract (destructive) migration(s): "
            f"{offenders}. The prior image needs schema a contract migration dropped; recover with a "
            "data-restore plan, not a rollback. Override with ALLOW_CONTRACT_ROLLBACK=1 only if you have one.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the unit test to verify it passes**

`uv run pytest tests/unit/test_rollback_guard_decision.py -v` → PASS.

- [ ] **Step 5: Write the alembic-walk functional test** (real migrations + a generated contract revision)

Create `tests/functional/{{ 'test_rollback_guard.py' if 'multitenantauth' in batteries else '' }}.jinja`:

```python
"""rollback_guard against the project's REAL alembic chains: clean head → allowed; a generated
contract migration in range → refused."""

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location("rollback_guard", Path("scripts/rollback_guard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_clean_chain_allows_rollback_to_prior_head():
    mod = _load()
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    head = script.get_current_head()
    prior = script.get_revision(head).down_revision or head
    # No shipped migration carries the contract marker → no offenders in range.
    assert mod._app_contract_in_range(prior) == []
    assert mod._control_contract_any() == []


def test_contract_migration_in_range_is_refused(tmp_path):
    mod = _load()
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    head_before = script.get_current_head()
    # Generate a real, chained revision, then mark it contract + add a drop.
    subprocess.run(
        ["alembic", "revision", "-m", "fwk66 contract probe", "--rev-id", "zzcontract"],
        check=True, capture_output=True, text=True,
    )
    new = next(p for p in Path("migrations/versions").glob("zzcontract*.py"))
    new.write_text("# deploy: contract\n" + new.read_text())
    try:
        offenders = mod._app_contract_in_range(head_before)
        assert any("zzcontract" in o for o in offenders)
        assert mod.main(["zzcontract" if False else head_before]) == 1  # refuse from old head
    finally:
        new.unlink()
```

- [ ] **Step 6: Run the functional test to verify it passes**

`TMPDIR=/var/tmp uv run pytest tests/functional/test_rollback_guard.py -v` → PASS.

- [ ] **Step 7: Commit**

```bash
git add "src/framework_cli/template/scripts/{{ 'rollback_guard.py' if 'multitenantauth' in batteries else '' }}" "src/framework_cli/template/tests/unit/.../test_rollback_guard_decision.py.jinja" "src/framework_cli/template/tests/functional/.../test_rollback_guard.py.jinja"
git commit -m "feat(FWK66): rollback_guard contract-floor (refuse image-only rollback across a contract migration)"
```

---

### Task 8: `strategy.sh` → jinja — image-only rollback + guard wiring + README

**Files:**
- Rename + modify: `src/framework_cli/template/infra/deploy/strategy.sh` → `infra/deploy/strategy.sh.jinja`
- Modify: `src/framework_cli/template/infra/deploy/README.md` (plane-aware section)
- Test: render-content + `bash -n` assertions in `tests/test_copier_runner.py`

**Interfaces:**
- Consumes: `scripts/rollback_guard.py` (Task 7); the existing `__target_*` hooks, `__target_release_history`, `__target_place_image`, `__target_record_release`.
- Produces: a `strategy.sh` whose battery render does image-only rollback (guard, no downgrade) and whose non-battery render is the verbatim pre-SP2 body (downgrade-then-redeploy).

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
import shutil
import subprocess


def _bash_n_ok(path: Path) -> bool:
    return subprocess.run(["bash", "-n", str(path)], capture_output=True).returncode == 0


def test_strategy_rollback_image_only_under_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["multitenantauth"]})
    sh = dest / "infra" / "deploy" / "strategy.sh"
    text = sh.read_text()
    assert "rollback_guard.py" in text
    assert "image-only" in text.lower()
    assert '__target_migrate "downgrade' not in text   # NO downgrade on any plane
    assert _bash_n_ok(sh)


def test_strategy_unchanged_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    sh = dest / "infra" / "deploy" / "strategy.sh"
    text = sh.read_text()
    assert '__target_migrate "downgrade ${rev}"' in text   # today's contract, verbatim
    assert "rollback_guard" not in text
    assert _bash_n_ok(sh)
```

- [ ] **Step 2: Run test to verify it fails**

`uv run pytest tests/test_copier_runner.py -k strategy -v`
Expected: FAIL — `rollback_guard.py` not present (and the file is still `strategy.sh`, not a jinja template).

- [ ] **Step 3: Rename + edit**

```bash
git mv src/framework_cli/template/infra/deploy/strategy.sh src/framework_cli/template/infra/deploy/strategy.sh.jinja
```

In `strategy.sh.jinja`, replace the body of `rollback()` (current lines 105–129) — keep the function signature and `require_var DEPLOY_ENV`, then branch:

```bash
rollback() {
  require_var DEPLOY_ENV
{%- if "multitenantauth" in batteries %}
  # Plane-aware (multitenantauth): IMAGE-ONLY rollback. Do NOT `alembic downgrade` — a downgrade
  # fan-out across the control plane + every tenant DB is an irreversible data-loss multiplier
  # (dropping auth/registry + customer columns). The expand-only contract (scripts/check_migrations.py)
  # guarantees the prior image runs against the current (forward) schema. A `# deploy: contract`
  # migration is a rollback FLOOR: scripts/rollback_guard.py refuses to cross one (override with a
  # data-restore plan: ALLOW_CONTRACT_ROLLBACK=1). Image-only rollback is NOT a data backup and
  # cannot rescue a contract migration — see infra/deploy/README.md.
  local history prev image rev
  history="$(__target_release_history)"
  if [ "$(printf '%s\n' "${history}" | grep -c .)" -lt 2 ]; then
    echo "::error::no previous release to roll back to (rollback target missing)." >&2
    exit 1
  fi
  prev="$(printf '%s\n' "${history}" | tail -n 2 | head -n 1)"
  image="$(printf '%s' "${prev}" | cut -f1)"
  rev="$(printf '%s' "${prev}" | cut -f2)"
  uv run python scripts/rollback_guard.py "${rev}"   # refuses if rolling back crosses a contract floor
  # shellcheck disable=SC2317  # reached once __target_place_image is implemented (not the _todo stub)
  APP_IMAGE="${image}" __target_place_image
  # shellcheck disable=SC2317
  __target_record_release "${image}" "${rev}"
{%- else %}
  # Roll back to the release before the current head: REVERSE migrations to ITS revision, THEN
  # redeploy ITS image. The downgrade is essential — the image only ever upgrades, so without it
  # the old code would run against the new schema. (Irreversible migrations cannot be restored;
  # the framework blocks them — see the migration guard + infra/deploy/README.md.)
  local history prev image rev
  history="$(__target_release_history)"
  # A rollback target must exist: need at least the current release + one prior.
  if [ "$(printf '%s\n' "${history}" | grep -c .)" -lt 2 ]; then
    echo "::error::no previous release to roll back to (rollback target missing)." >&2
    exit 1
  fi
  prev="$(printf '%s\n' "${history}" | tail -n 2 | head -n 1)"
  image="$(printf '%s' "${prev}" | cut -f1)"
  rev="$(printf '%s' "${prev}" | cut -f2)"
  __target_migrate "downgrade ${rev}"
  # shellcheck disable=SC2317  # reached once __target_migrate is implemented (not the _todo stub)
  APP_IMAGE="${image}" __target_place_image
  # Record the rollback as the new live release so the durable history reflects what is now
  # deployed (`current-release`/`releases` track live state, not just forward deploys). A later
  # rollback then walks back from HERE (its prior = the release this rollback superseded).
  # shellcheck disable=SC2317  # reached once the hooks are implemented (not the _todo stubs)
  __target_record_release "${image}" "${rev}"
{%- endif %}
}
```

The `{% else %}` branch is the **verbatim** pre-SP2 `rollback()` body — so a non-battery render is byte-equivalent to today's file (only `rollback()` carries jinja; the rest of the file is unchanged). No other function changes.

- [ ] **Step 4: Update `infra/deploy/README.md`**

Add a section (find the deploy/rollback discussion; if the file is `README.md.jinja`, edit that source):

```markdown
## Plane-aware migrate & rollback (multitenantauth)

With the `multitenantauth` battery, a project has THREE database planes: the control plane, the
default business DB, and one DB per tenant. Migration and rollback are plane-aware:

- **Migrate fan-out.** Boot (`scripts/entrypoint.sh`) and `task db:migrate:all` run
  `python -m <pkg>.multitenantauth.tenancy.migrate`: the control plane first, then the default DB,
  then every active tenant DB. For a multi-host rolling deploy, set `APP_RUN_MIGRATIONS=false` on the
  app hosts and run `task db:migrate:all` ONCE before the roll so N containers don't race.
- **Rollback is image-only.** Deploy rollback redeploys the prior image and performs **no
  `alembic downgrade` on any plane** — a downgrade fan-out across the control plane + N tenant DBs
  would irreversibly drop auth/registry + customer data. Safety rests on the **expand-only** contract
  (`scripts/check_migrations.py`, now enforced on both chains): every migration is additive, so the
  prior image runs against the current schema.
- **Contract migrations are a rollback floor.** A `# deploy: contract` (destructive) migration cannot
  be crossed by an image-only rollback — the prior image needs schema it dropped. `scripts/rollback_guard.py`
  refuses such a rollback; override with `ALLOW_CONTRACT_ROLLBACK=1` only if you have a data-restore plan.
  Image-only rollback is **not** a data backup. (A control-plane contract migration is rare and maximally
  dangerous — treat it as a manual, coordinated, non-one-click operation.)
- **Cruft.** Because rollback never downgrades, a rolled-back feature leaves its additive schema behind
  (N× across tenant DBs). Reclaim it later with a deliberate forward-only contract migration.
```

- [ ] **Step 5: Run tests + integrity to verify they pass**

`uv run pytest tests/test_copier_runner.py -k strategy -v` → PASS (both).
Confirm the rename didn't break classification: re-render `--with multitenantauth` and baseline; `framework integrity --ci` → OK on both (the rendered path `infra/deploy/strategy.sh` is unchanged). Run the FWK29 surface guard: `uv run pytest tests/runtime_coverage -q` → green (no new/over-broad surface).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/infra/deploy/strategy.sh.jinja src/framework_cli/template/infra/deploy/README.md tests/test_copier_runner.py
git commit -m "feat(FWK66): plane-aware image-only rollback + contract floor in strategy.sh (battery), non-battery unchanged"
```

---

## Self-Review

**1. Spec coverage** (each spec section → task):
- §2 migrate fan-out → Task 2; `active_tenant_dsns` → Task 1; entrypoint → Task 4; `db:migrate:all` → Task 5; plane-aware deploy/rollback → Task 8; `check_migrations` both chains → Task 6; multi-host doc → Task 8 README; conformance real-PG → Task 3; non-battery identity → Tasks 4/5/8 negative tests.
- §4.1 `upgrade_all` ordering/failure → Task 2 unit tests. §4.2 `active_tenant_dsns` active-only → Task 1. §4.5 image-only rollback + contract floor → Tasks 7+8. §4.6 both-chains scan → Task 6. §4.7 integrity lock → Task 2 Step 4.
- §6 never-log-DSN → Task 2 `test_report_never_contains_dsn_or_message`. §7 conformance tiers → Tasks 2 (unit), 3 (real-PG never-skip-neutral), 4/5/8 (non-battery). §8 Layer-2 gate → Execution section below.

**2. Placeholder scan:** none — every code step has full code; the only deliberate deferral (per-release control-rev tracking for a precise control floor) is documented as a future enhancement in `rollback_guard.py`, not a plan gap.

**3. Type consistency:** `active_tenant_dsns(session) -> list[tuple[str,str]]` (Task 1) is consumed unchanged in Task 2 (`for tenant_id, dsn in targets`). `upgrade_all` returns the dict shape consumed by `report_failed` (Task 2) and asserted in Task 3. `migrate_tenant(dsn)` (existing) is reused verbatim. `rollback_guard.main(argv)`/`_app_contract_in_range`/`_control_contract_any`/`_has_marker` (Task 7) are the exact names Task 8 calls (`python scripts/rollback_guard.py "${rev}"`).

**Note for the implementer:** verify the engine-registry reset helper name in `tenancy/engine_registry.py` (used in Task 3 as `reset_tenant_engines`) and `invalidate_dsn_cache`'s no-arg form against `tenancy/session.py` before running Task 3 — match SP1's `test_tenant_provisioning.py` usage exactly.

## Execution & Review (project policy — restated per [[subagent-review-model-pattern]])

- **Subagent-driven**, author/verify split: implementer subagents **author** code (no docker — they stream-idle on long docker turns); the **controller runs** the real-Postgres/render verification on its own bash. Per-task **code-quality review = Opus**; spec-compliance review = Sonnet; implementers = Sonnet (Haiku for trivial). Pass `model` explicitly per role.
- **Gate cadence** ([[gate-cadence-framework-slices]]): lighter per-task review + controller skip-marker commits ([[controller-skip-marker-recipe]]); the commit-gate hook needs `PLAN.md`/`ACTION_LOG.md` staged ([[commit-gate-hook-timing]] — separate `git add` then `git commit`, keep "commit" out of Bash descriptions). Tick the PLAN task + append an ACTION_LOG entry as work completes.
- **Branch-end gates:** (1) whole-branch Opus code-quality review; (2) **Phase-2 Layer-2 adversarial security pass** — stance×focus matrix, **all stages Opus** ([[security-review-workflow-all-opus]]) — scoped to migrate/deploy/rollback, explicitly covering the **migration-data-safety** cell (can a crafted migration / fan-out ordering / rollback path destroy or cross-contaminate tenant data?). Gate rule: 0 confirmed Critical/High. Scorecard under `docs/superpowers/eval-scorecards/`.
- **Release readiness** ([[release-readiness-needs-render-not-local-gate]]): before cutting the Phase-2 release, render baseline + `--with multitenantauth` + all-batteries and run their own `ruff`/`ruff format --check`/`mypy`; this ships a template-payload release.
- **Promote-up:** advance `DEC-0005` toward the conformance contract; relay the corrected DEC-0004 drift note + request Meridian's async confirmation.
