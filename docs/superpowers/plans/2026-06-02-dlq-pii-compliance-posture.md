# DLQ-PII Compliance Posture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dead-letter queue private by default — redact task args + traceback unless a task opts into raw storage — and tag opt-in rows for easy erasure.

**Architecture:** The `workers` battery's `BaseTask` gains redact-by-default seams (`dlq_args_json` flipped to shape-only; new `dlq_traceback` keeping stack+type, message redacted). `on_failure` derives a `redacted` boolean (true iff both seams are the framework defaults) and persists it to a new `dead_letter_tasks.redacted` column via a tail alembic migration. Plus two hygiene items (beat-task prune error-handling + `triggered_by` audit attribution), docs, and retiring `DEC-0002`.

**Tech Stack:** Python 3.12, Celery, SQLAlchemy + Alembic, structlog, pytest. **Two kinds of code:** (a) `src/framework_cli/migrations.py` is **framework source** — normal `uv run pytest`/`mypy`/`ruff`. (b) Everything under `src/framework_cli/template/` is **template payload** — validated via the render loop (`[[template-payload-tdd-loop]]`): render a `--with workers --with webhooks` project into a tmp dir, `uv sync`, run the generated project's own tests; `ruff format`-check the rendered output. Full alembic-on-Postgres validation is the CI acceptance tier; locally, verify the rendered migration is well-formed + the hermetic SQLite tests (table-create, not alembic) pass.

**Spec:** `docs/superpowers/specs/2026-06-02-dlq-pii-compliance-posture-design.md`

---

## File Structure

- **Modify** `src/framework_cli/migrations.py` (framework) — add `migration_head()` + `down_revision_dlq_redacted` to `migration_context`. (`copier_runner.py` already merges `migration_context`, so the new var flows automatically — no change there.)
- **Create** `src/framework_cli/template/migrations/versions/{{ '0007_dlq_redacted_flag.py' if 'workers' in batteries else '' }}.jinja` — tail migration adding the column.
- **Modify** `…/tasks/dead_letter.py` — `DeadLetterTask.redacted` column, `record_failure(redacted=)`, `triggered_by` on the `dlq_pruned` log.
- **Modify** `…/tasks/base.py` — flip `dlq_args_json`, add `dlq_traceback`, set `redacted` in `on_failure`.
- **Modify** `…/webhooks/inbox.py` — `triggered_by` on the `webhook_inbox_pruned` log.
- **Modify** `…/tasks/retention.py.jinja` — try/except + `*_prune_failed` error logs.
- **Modify** `README.md.jinja` — privacy-by-default + erasure-scoping note.
- **Modify** `docs/superpowers/decisions/DEC-0002-dlq-args-json-opt-in-redaction.md` (framework) — retire.
- **Tests:** framework `tests/test_migrations.py`; template `tests/unit/test_dlq_redaction.py.jinja` (+ retention/inbox tests).

The brace-named path `{% if "workers" in batteries %}tasks{% endif %}` is the real on-disk directory name for `base.py`/`dead_letter.py`/`retention.py.jinja`; `{% if "webhooks" in batteries %}webhooks{% endif %}` for `inbox.py`.

---

### Task 1: `migrations.py` — chain head for the tail migration (framework source)

**Files:**
- Modify: `src/framework_cli/migrations.py`
- Test: `tests/test_migrations.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_migrations.py
from framework_cli.migrations import migration_context, migration_head

def test_migration_head_is_last_present_battery():
    assert migration_head([]) == "0001"
    assert migration_head(["workers"]) == "0003"
    assert migration_head(["webhooks", "workers"]) == "0003"
    assert migration_head(["workers", "pgvector"]) == "0004"
    assert migration_head(["workers", "age"]) == "0006"  # age (0006) is the head

def test_migration_context_includes_dlq_redacted_down_revision():
    # the tail migration (workers-gated) chains off whatever the current head is
    assert migration_context(["workers"])["down_revision_dlq_redacted"] == "0003"
    assert migration_context(["workers", "age"])["down_revision_dlq_redacted"] == "0006"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_migrations.py -k "head or dlq_redacted" -q`
Expected: FAIL — `ImportError: cannot import name 'migration_head'`.

- [ ] **Step 3: Write minimal implementation**

In `src/framework_cli/migrations.py`, add `migration_head` and extend `migration_context`:

```python
def migration_head(batteries: Sequence[str]) -> str:
    """The chain head: the revision of the last present migration-adding battery (canonical
    order), else the baseline '0001'. A tail migration (e.g. the DLQ redacted flag) chains
    off this so it runs after every battery migration."""
    present = [b for b in MIGRATION_ORDER if b in batteries]
    return REVISIONS[present[-1]] if present else "0001"


def migration_context(batteries: Sequence[str]) -> dict[str, str]:
    """Copier context vars `down_revision_<battery>` for each present migration battery,
    plus `down_revision_dlq_redacted` for the workers-gated DLQ redacted-flag tail migration."""
    ctx = {
        f"down_revision_{b}": rev
        for b, rev in migration_down_revisions(batteries).items()
    }
    ctx["down_revision_dlq_redacted"] = migration_head(batteries)
    return ctx
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_migrations.py -q`
Expected: PASS (new + the 5 pre-existing migration tests).

- [ ] **Step 5: Commit** (controller-committed — framework source, 0-agent gate; per the working agreement, stage `CLAUDE.md` too after updating its Current State)

```bash
git add src/framework_cli/migrations.py tests/test_migrations.py CLAUDE.md
git commit -m "feat(migrations): chain-head helper for the DLQ redacted-flag tail migration"
```

---

### Task 2: `redacted` column — model, migration, `record_failure` (template payload)

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/dead_letter.py`
- Create: `src/framework_cli/template/migrations/versions/{{ '0007_dlq_redacted_flag.py' if 'workers' in batteries else '' }}.jinja`
- Test: `src/framework_cli/template/tests/unit/{{ 'test_dlq_redaction.py' if 'workers' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing test** (append to the rendered project's `tests/unit/test_dlq_redaction.py`)

```python
def test_record_failure_persists_redacted_flag():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from {{ package_name }}.tasks import dead_letter

    engine = create_engine("sqlite://")
    dead_letter.DeadLetterTask.__table__.create(engine)
    s = Session(engine)
    dead_letter.record_failure(
        s, task_name="t", task_id="1", args_json="{}", traceback="tb", redacted=False
    )
    row = dead_letter.list_recent(s)[0]
    assert row.redacted is False
```

(Match the existing `test_dlq_redaction.py` import/style; read it first.)

- [ ] **Step 2: Render + run to verify it fails**

```bash
FW="$(pwd)"; rm -rf /tmp/dlqpii; mkdir /tmp/dlqpii; cd /tmp/dlqpii
uv run --project "$FW" framework new "dlqpii" --with workers --with webhooks >/dev/null
cd dlqpii && uv sync --quiet
uv run pytest tests/unit/test_dlq_redaction.py -k redacted_flag -q
```
Expected: FAIL — `TypeError: record_failure() got an unexpected keyword argument 'redacted'` (and no `redacted` attribute).

- [ ] **Step 3: Implement** (edit the TEMPLATE files, then re-render)

In `dead_letter.py`: add `Boolean` to the `sqlalchemy` import; add the column to `DeadLetterTask` (after `traceback`); add `redacted` to `record_failure`:

```python
# import: from sqlalchemy import (Boolean, CursorResult, DateTime, Integer, String, Text, delete, func, select, text)

    redacted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
```

```python
def record_failure(
    session: Session,
    *,
    task_name: str,
    task_id: str,
    args_json: str,
    traceback: str,
    redacted: bool,
) -> None:
    """Persist a terminally-failed task. Commits its own transaction (called from on_failure).

    `redacted` is True iff the task used the framework's default redact-by-default seams (so
    the row holds no personal data); False means a task opted into raw storage — scope any
    erasure with `WHERE redacted = false`."""
    session.add(
        DeadLetterTask(
            task_name=task_name,
            task_id=task_id,
            args_json=args_json,
            traceback=traceback,
            redacted=redacted,
        )
    )
    session.commit()
```

Create the migration `migrations/versions/{{ '0007_dlq_redacted_flag.py' if 'workers' in batteries else '' }}.jinja`:

```python
"""dlq redacted flag

Revision ID: 0007
Revises: {{ down_revision_dlq_redacted }}

"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "{{ down_revision_dlq_redacted }}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dead_letter_tasks",
        sa.Column(
            "redacted", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
    )


def downgrade() -> None:
    op.drop_column("dead_letter_tasks", "redacted")
```

- [ ] **Step 4: Re-render + verify pass**

```bash
FW="<framework root>"; cd /tmp/dlqpii && rm -rf dlqpii
uv run --project "$FW" framework new "dlqpii" --with workers --with webhooks >/dev/null
cd dlqpii && uv sync --quiet
uv run pytest tests/unit/test_dlq_redaction.py -q   # new + existing pass
uv run mypy src && uv run ruff check . && uv run ruff format --check src/*/tasks/dead_letter.py
# Verify the migration rendered with a resolved down_revision (workers+webhooks → head 0003):
grep -n 'down_revision = "0003"' migrations/versions/0007_dlq_redacted_flag.py
```
Expected: tests pass; mypy/ruff clean; `down_revision = "0003"` present (NOT the literal `{{ ... }}`). **Note:** if SQLite rejects `server_default=sa.text("true")` in the hermetic table-create, change both the model and migration to `sa.text("1")` (SQLite-portable; Postgres accepts it for boolean) and re-verify. Full alembic-upgrade validation is the CI acceptance tier.

- [ ] **Step 5: Commit** (template payload — integration; stage + skip-marker gate, then controller-commit per the cadence; update CLAUDE.md first)

```bash
# (controller) git add the template files + CLAUDE.md; finalize the gate marker; commit
git commit -m "feat(template): dead_letter.redacted column + tail migration 0007 + record_failure(redacted)"
```

---

### Task 3: `base.py` redact-by-default seams + `on_failure` (template payload)

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/base.py`
- Test: `…/tests/unit/{{ 'test_dlq_redaction.py' if 'workers' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing tests** (append to the rendered `test_dlq_redaction.py`)

```python
def test_dlq_args_json_default_is_shape_only():
    from {{ package_name }}.tasks.base import BaseTask

    out = BaseTask().dlq_args_json(("alice@example.com", {"ssn": "123"}), {"token": "x"})
    assert "alice@example.com" not in out and "123" not in out and "token" not in out
    import json as _j
    data = _j.loads(out)
    assert data == {"args": ["str", "dict"], "kwargs": 1}


def test_dlq_traceback_default_redacts_message_keeps_type():
    from {{ package_name }}.tasks.base import BaseTask

    try:
        raise ValueError("leak alice@example.com")
    except ValueError as exc:
        tb = BaseTask().dlq_traceback(exc, None)
    assert "alice@example.com" not in tb
    assert "ValueError: <redacted>" in tb
    assert "test_dlq" in tb  # stack frame retained (debuggable)


def test_on_failure_sets_redacted_true_for_default_task(monkeypatch):
    # A plain BaseTask subclass uses the default seams → redacted=True.
    import {{ package_name }}.tasks.base as base_mod
    from {{ package_name }}.tasks import dead_letter

    captured = {}

    def fake_record(session, **kw):
        captured.update(kw)

    monkeypatch.setattr(dead_letter, "record_failure", fake_record)

    class _SL:
        def __enter__(self): return object()
        def __exit__(self, *a): return False

    monkeypatch.setattr(base_mod, "SessionLocal", lambda: _SL())
    try:
        raise ValueError("x")
    except ValueError as exc:
        base_mod.BaseTask().on_failure(exc, "tid", ("a",), {}, einfo=None)
    assert captured["redacted"] is True


def test_on_failure_sets_redacted_false_when_seam_overridden(monkeypatch):
    import {{ package_name }}.tasks.base as base_mod
    from {{ package_name }}.tasks import dead_letter

    captured = {}
    monkeypatch.setattr(dead_letter, "record_failure", lambda session, **kw: captured.update(kw))

    class _SL:
        def __enter__(self): return object()
        def __exit__(self, *a): return False

    monkeypatch.setattr(base_mod, "SessionLocal", lambda: _SL())

    class RawTask(base_mod.BaseTask):
        def dlq_args_json(self, args, kwargs):
            return "full"

    try:
        raise ValueError("x")
    except ValueError as exc:
        RawTask().on_failure(exc, "tid", ("a",), {}, einfo=None)
    assert captured["redacted"] is False
```

- [ ] **Step 2: Render + run to verify they fail**

Re-render (as Task 2 Step 2) and: `uv run pytest tests/unit/test_dlq_redaction.py -q`
Expected: FAIL — old `dlq_args_json` returns full args; no `dlq_traceback`; `record_failure` called without `redacted`.

- [ ] **Step 3: Implement** (edit TEMPLATE `base.py`)

```python
# imports: add `import traceback` (keep `import json`, `from typing import Any`)

    def dlq_args_json(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        """Default: store the SHAPE of the call (arg types + kwarg count), never the values —
        the dead-letter row carries no personal data. OVERRIDE to serialize full args for a
        task you know carries no PII (you then own the erasure obligation; see dead_letter
        `redacted`)."""
        return json.dumps({"args": [type(a).__name__ for a in args], "kwargs": len(kwargs)})

    def dlq_traceback(self, exc: Exception, einfo: Any) -> str:
        """Default: full stack + exception type, message redacted (interpolated PII lives in
        the message). OVERRIDE to return str(einfo) for a task known PII-free."""
        stack = "".join(traceback.format_tb(exc.__traceback__))
        return f"{stack}{type(exc).__name__}: <redacted>"

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """Called once retries are exhausted — drain to the dead-letter queue.

        `redacted` is True iff this task uses the framework's default redact-by-default seams;
        a task overriding either seam (to store raw args/traceback) flags its rows redacted=False
        so erasure can be scoped to them.
        """
        redacted = (
            type(self).dlq_args_json is BaseTask.dlq_args_json
            and type(self).dlq_traceback is BaseTask.dlq_traceback
        )
        with SessionLocal() as session:
            dead_letter.record_failure(
                session,
                task_name=self.name or "unknown",
                task_id=task_id,
                args_json=self.dlq_args_json(args, kwargs),
                traceback=self.dlq_traceback(exc, einfo),
                redacted=redacted,
            )
```

- [ ] **Step 4: Re-render + verify pass**

Re-render; `uv run pytest tests/unit/test_dlq_redaction.py -q` (all pass); `uv run mypy src && uv run ruff check . && uv run ruff format --check src/*/tasks/base.py`.
Expected: PASS; clean.

- [ ] **Step 5: Commit** (template integration — skip-marker gate, controller-commit; update CLAUDE.md first)

```bash
git commit -m "feat(template): DLQ redact-by-default seams (args shape-only, traceback message-redacted) + redacted derivation"
```

---

### Task 4: Hygiene — `triggered_by` + beat-task prune error handling (template payload)

**Files:**
- Modify: `…/tasks/dead_letter.py` (the `dlq_pruned` log), `…/webhooks/inbox.py` (the `webhook_inbox_pruned` log), `…/tasks/retention.py.jinja`
- Test: `…/tests/unit/{{ 'test_dlq_retention.py' if 'workers' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing tests**

Add to the rendered `test_dlq_retention.py` (it already uses `structlog.testing.capture_logs`):

```python
def test_prune_logs_triggered_by():
    s = _session()
    _add(s, days_ago=40)
    with structlog.testing.capture_logs() as logs:
        dead_letter.prune_expired(s, retention_days=30)
    assert any(
        e.get("event") == "dlq_pruned" and e.get("triggered_by") == "prune_expired_records"
        for e in logs
    )


def test_prune_expired_records_logs_failure(monkeypatch):
    import structlog

    from {{ package_name }}.tasks import dead_letter, retention

    def boom(session, retention_days):
        raise RuntimeError("db down")

    monkeypatch.setattr(dead_letter, "prune_expired", boom)
    with structlog.testing.capture_logs() as logs:
        retention.prune_expired_records()
    assert any(e.get("event") == "dlq_prune_failed" for e in logs)
```

- [ ] **Step 2: Render + run to verify they fail**

Re-render; `uv run pytest tests/unit/test_dlq_retention.py -k "triggered_by or logs_failure" -q`
Expected: FAIL — no `triggered_by` field; `prune_expired_records` propagates the error (no `dlq_prune_failed`).

- [ ] **Step 3: Implement** (edit TEMPLATE files)

In `dead_letter.py` `prune_expired`, add the field:
```python
    get_logger().info(
        "dlq_pruned",
        rows_deleted=deleted,
        retention_days=retention_days,
        triggered_by="prune_expired_records",
    )
```

In `inbox.py` `prune_expired`, the analogous log:
```python
    get_logger().info(
        "webhook_inbox_pruned",
        rows_deleted=deleted,
        retention_days=retention_days,
        triggered_by="prune_expired_records",
    )
```

Rewrite `retention.py.jinja`'s task body to wrap each prune (re-introduce `get_logger`):
```python
from __future__ import annotations

from ..config.settings import get_settings
from ..db.engine import SessionLocal
from ..logging_config import get_logger
from . import dead_letter
from .app import app


@app.task
def prune_expired_records() -> None:
    # Each prune is independent + self-logging (dlq_pruned / webhook_inbox_pruned). A prune that
    # raises is an operational/retention-compliance signal, so log it (dlq_prune_failed /
    # webhook_inbox_prune_failed) rather than letting the beat task die silently.
    settings = get_settings()
    log = get_logger()
    with SessionLocal() as session:
        try:
            dead_letter.prune_expired(session, settings.dlq_retention_days)
        except Exception as exc:
            log.error("dlq_prune_failed", error=str(exc))
{%- if "webhooks" in batteries %}

    from ..webhooks import inbox

    with SessionLocal() as session:
        try:
            inbox.prune_expired(session, settings.webhook_inbox_retention_days)
        except Exception as exc:
            log.error("webhook_inbox_prune_failed", error=str(exc))
{%- endif %}
```

- [ ] **Step 4: Re-render + verify pass**

Re-render; `uv run pytest tests/unit/test_dlq_retention.py tests/unit/test_webhook_inbox_retention.py -q`; `uv run ruff check . && uv run ruff format --check src/*/tasks/retention.py src/*/tasks/dead_letter.py src/*/webhooks/inbox.py && uv run mypy src`.
Expected: PASS; clean.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(template): beat-task prune error logging + triggered_by audit attribution"
```

---

### Task 5: Docs, retire DEC-0002, full verification

**Files:**
- Modify: `src/framework_cli/template/README.md.jinja`
- Modify: `docs/superpowers/decisions/DEC-0002-dlq-args-json-opt-in-redaction.md`

- [ ] **Step 1: Update the README DLQ note**

Replace the existing sentence (currently: *"The DLQ stores task args, which may contain PII — override `BaseTask.dlq_args_json` to redact sensitive fields before they're dead-lettered."*) with:

```
The DLQ stores **no personal data by default**: args are reduced to their shape (types + kwarg count) and the traceback keeps the stack + exception type with the message redacted. To store full args/traceback for a task you know is PII-free, override `BaseTask.dlq_args_json` / `BaseTask.dlq_traceback` — those rows are then flagged `redacted=false`, and you own the erasure obligation (scope any right-to-be-forgotten request with `WHERE redacted = false`). (Note: the original exception/traceback may still reach your logs via Celery's own failure logging — log-surface scrubbing is a separate concern.)
```

- [ ] **Step 2: Retire DEC-0002**

Edit `docs/superpowers/decisions/DEC-0002-dlq-args-json-opt-in-redaction.md`: change `status: deferred` → `status: retired`, and append to the body:

```
RETIRED 2026-06-02: superseded by the DLQ-PII compliance-posture slice — the redaction
default was flipped to redact-by-default (spec 2026-06-02-dlq-pii-compliance-posture-design.md),
so the opt-in-default concern is resolved, not merely acknowledged.
```

- [ ] **Step 3: Verify decisions loader drops the retired decision**

Run: `uv run python -c "from pathlib import Path; from framework_cli.review.decisions import relevant_decisions, active_decision_ids; print('compliance:', [d.id for d in relevant_decisions('compliance', Path('.'))]); print('active:', sorted(active_decision_ids(Path('.'))))"`
Expected: `compliance: []` (DEC-0002 no longer active) and `active: ['DEC-0001']`.

- [ ] **Step 4: Full verification — render the key combos + framework gate**

```bash
# framework source gate
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q --ignore=tests/acceptance
# rendered project (workers + webhooks): its own suite + lint + the rendered migration
FW="$(pwd)"; cd /tmp/dlqpii && rm -rf dlqpii
uv run --project "$FW" framework new "dlqpii" --with workers --with webhooks >/dev/null
cd dlqpii && uv sync --quiet && uv run pytest tests/unit -q && uv run mypy src && uv run ruff check .
grep -n 'down_revision = "0003"' migrations/versions/0007_dlq_redacted_flag.py
# also render workers-only and workers+age to confirm the tail migration's down_revision resolves to the head
cd /tmp/dlqpii && rm -rf wonly && uv run --project "$FW" framework new "wonly" --with workers >/dev/null && grep -n 'down_revision = "0003"' wonly/migrations/versions/0007_dlq_redacted_flag.py
rm -rf wage && uv run --project "$FW" framework new "wage" --with workers --with age >/dev/null && grep -n 'down_revision = "0006"' wage/migrations/versions/0007_dlq_redacted_flag.py
```
Expected: framework suite green, ruff/format/mypy clean; rendered project's unit tests green; the tail migration's `down_revision` resolves to `0003` (workers-only / workers+webhooks) and `0006` (workers+age) — confirming the chain head computation.

- [ ] **Step 5: Commit**

```bash
git commit -m "docs(template): DLQ privacy-by-default note + erasure scoping; retire DEC-0002"
```

---

## Self-Review

**Spec coverage:**
- §3 args shape-only default → Task 3 (`dlq_args_json` flip + test).
- §4 `dlq_traceback` seam → Task 3 (seam + `on_failure` uses it + test).
- §5 `redacted` flag (derived) → Task 2 (column + `record_failure`) + Task 3 (`on_failure` derivation + true/false tests).
- §6 hygiene (prune error handling + `triggered_by`) → Task 4.
- §7 migration (additive, tail) + upskill-safe + retire DEC-0002 → Task 1 (head computation) + Task 2 (migration `0007`) + Task 5 (DEC-0002).
- §8 docs → Task 5.
- §9 tests → each task is TDD; the `redacted` true/false, args-shape, traceback-message-redacted, `triggered_by`, and prune-failure cases are all covered.

**Placeholder scan:** none — every step shows code/commands + expected output. The one conditional (SQLite `true` vs `1` server_default) is an explicit verify-and-adjust instruction, not a placeholder.

**Type consistency:** `record_failure(..., redacted: bool)` (Task 2) matches the `on_failure` call (Task 3). `migration_head(batteries)` / `down_revision_dlq_redacted` (Task 1) match the migration's `{{ down_revision_dlq_redacted }}` (Task 2). The `redacted` column name is consistent across model, migration, `record_failure`, `on_failure`, README, and tests. Seam names `dlq_args_json`/`dlq_traceback` consistent across base.py, the `on_failure` identity check, and tests.

**Migration validation gap (called out):** the hermetic tests use SQLite `__table__.create` (not alembic). The migration `0007`'s correctness on Postgres (apply/reverse, chain integrity) is validated by the CI acceptance tier; locally we verify it renders with a resolved `down_revision`. If a stronger local signal is wanted, the implementer may run the Docker acceptance subset for `--with workers` — but mind the `/tmp` hygiene caveat.
