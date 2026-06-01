# DLQ / Webhook-Inbox Retention + Redaction Seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the generated app config-driven retention for the dead-letter queue + webhook inbox (a daily pruning beat task) and an overridable seam to redact PII before it's written to the DLQ.

**Architecture:** Add `prune_expired(session, retention_days)` to the DLQ and inbox modules, a daily `prune_expired_records` Celery beat task that calls them (inbox jinja-gated on the webhooks battery), retention-day settings knobs, and an overridable `BaseTask.dlq_args_json` that `on_failure` routes through. Defaults preserve current behavior.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (`delete()`), Celery (beat), pydantic-settings, Copier (Jinja) template, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-01-dlq-pii-retention-design.md`

---

## Conventions (read first)

- `FW` = framework repo root (`/home/chris/Claude Code/Projects/framework/swiftwater-framework`). You are on branch `dlq-pii-retention-2026-06-01` — do NOT switch branches.
- **Template payload.** The edited files render into generated projects; their tests run in a GENERATED project (which has SQLAlchemy/Celery installed). Rendered-project loop (one-time, ALL batteries so workers+webhooks are present):
  ```bash
  rm -rf /tmp/dq-work && uv run framework template-render --out /tmp/dq-work >/dev/null
  (cd /tmp/dq-work && uv sync --quiet)
  ```
  Mirror after editing: plain `.py` (`dead_letter.py`, `inbox.py`, `base.py`) → `cp` template source to the rendered path; `.jinja` files → re-render to `/tmp/dq-render` and `cp` the rendered file. Run: `(cd /tmp/dq-work && uv run pytest <test> -q)`.
- **Brace paths** must be quoted in shell. tasks dir = `src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/`; webhooks dir = `src/{{package_name}}/{% if "webhooks" in batteries %}webhooks{% endif %}/`.
- **COMMIT-GATE HOOK:** blocks `git commit` unless `CLAUDE.md` is staged. Per commit: brief Current-State note + bump Last updated; `git add CLAUDE.md <files>` (separate); then `git commit` (own command; keep "commit" out of Bash descriptions). Trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. In a subagent session the gate may BLOCK (needs the `Workflow` tool subagents lack) — if so, stage everything + report DONE; the controller commits.
- **Do NOT run the Docker acceptance tier.**
- **SQLite/tz note:** prune compares the timestamp column to a Python `datetime.now(UTC) - timedelta(days=…)`. In tests, insert rows with **timezone-aware** `failed_at`/`received_at` (UTC) so the ISO-string comparison on SQLite is consistent with the tz-aware cutoff.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/{{package_name}}/config/settings.py.jinja` | `dlq_retention_days` (workers) + `webhook_inbox_retention_days` (webhooks) | 1 |
| `src/{{package_name}}/{…tasks…}/dead_letter.py` | `prune_expired` | 1 |
| `src/{{package_name}}/{…webhooks…}/inbox.py` | `prune_expired` | 1 |
| `tests/unit/{{ 'test_dlq_retention.py' if 'workers' in batteries else '' }}.jinja` | DLQ prune + schedule-wiring tests | 1, 2 |
| `tests/unit/{{ 'test_webhook_inbox_retention.py' if 'webhooks' in batteries else '' }}.jinja` | inbox prune test | 1 |
| `src/{{package_name}}/{…tasks…}/retention.py.jinja` | `prune_expired_records` beat task | 2 |
| `src/{{package_name}}/{…tasks…}/schedule.py.jinja` | register daily prune | 2 |
| `src/{{package_name}}/{…tasks…}/app.py.jinja` | add `retention` to Celery `include` | 2 |
| `src/{{package_name}}/{…tasks…}/base.py` | `dlq_args_json` seam | 3 |
| `tests/unit/{{ 'test_workers_unit.py' … }}.jinja` (or a new gated file) | redaction-seam test | 3 |
| `README.md.jinja` | retention env vars + redaction note | 4 |

---

## Task 1: Retention config + prune functions

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja`
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/dead_letter.py`
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "webhooks" in batteries %}webhooks{% endif %}/inbox.py`
- Create: `src/framework_cli/template/tests/unit/{{ 'test_dlq_retention.py' if 'workers' in batteries else '' }}.jinja`
- Create: `src/framework_cli/template/tests/unit/{{ 'test_webhook_inbox_retention.py' if 'webhooks' in batteries else '' }}.jinja`

- [ ] **Step 1: Add the settings knobs**

In `config/settings.py.jinja`, in the `{%- if "webhooks" in batteries %}` block, after `webhook_signing_secret: str = ""`, add:
```python
    # Inbox dedup rows are pruned after this many days. Keep >= your provider's webhook
    # redelivery window, or a late retry could be processed twice.
    webhook_inbox_retention_days: int = 7
```
In the `{%- if "workers" in batteries %}` block, after `celery_result_backend: str = "redis://redis:6379/1"`, add:
```python
    # Dead-letter rows (terminal task failures) are pruned after this many days.
    dlq_retention_days: int = 30
```

- [ ] **Step 2: Write the failing prune tests**

Create `tests/unit/{{ 'test_dlq_retention.py' if 'workers' in batteries else '' }}.jinja`:
```python
"""DLQ retention pruning (hermetic — in-memory SQLite, no broker/Postgres)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from {{ package_name }}.tasks import dead_letter


def _session() -> Session:
    engine = create_engine("sqlite://")
    dead_letter.DeadLetterTask.__table__.create(engine)
    return Session(engine)


def _add(session: Session, *, days_ago: int) -> None:
    session.add(
        dead_letter.DeadLetterTask(
            task_name="t",
            task_id=f"id-{days_ago}",
            args_json="[]",
            traceback="",
            failed_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    session.commit()


def test_prune_expired_deletes_only_old_rows():
    s = _session()
    _add(s, days_ago=40)
    _add(s, days_ago=1)
    deleted = dead_letter.prune_expired(s, retention_days=30)
    assert deleted == 1
    assert dead_letter.count(s) == 1  # the recent row survives
```

Create `tests/unit/{{ 'test_webhook_inbox_retention.py' if 'webhooks' in batteries else '' }}.jinja`:
```python
"""Webhook-inbox retention pruning (hermetic — in-memory SQLite)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from {{ package_name }}.webhooks import inbox
from {{ package_name }}.webhooks.models import WebhookEvent


def _session() -> Session:
    engine = create_engine("sqlite://")
    WebhookEvent.__table__.create(engine)
    return Session(engine)


def _add(session: Session, key: str, *, days_ago: int) -> None:
    session.add(
        WebhookEvent(
            idempotency_key=key,
            received_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    session.commit()


def test_prune_expired_deletes_only_old_rows():
    s = _session()
    _add(s, "old", days_ago=30)
    _add(s, "new", days_ago=1)
    deleted = inbox.prune_expired(s, retention_days=7)
    assert deleted == 1
    assert s.scalar(select(func.count()).select_from(WebhookEvent)) == 1
```

Mirror both (render + cp) and run:
```bash
rm -rf /tmp/dq-render && uv run framework template-render --out /tmp/dq-render >/dev/null
cp /tmp/dq-render/tests/unit/test_dlq_retention.py /tmp/dq-work/tests/unit/test_dlq_retention.py
cp /tmp/dq-render/tests/unit/test_webhook_inbox_retention.py /tmp/dq-work/tests/unit/test_webhook_inbox_retention.py
(cd /tmp/dq-work && uv run pytest tests/unit/test_dlq_retention.py tests/unit/test_webhook_inbox_retention.py -q)
```
Expected: FAIL — `AttributeError: module ... has no attribute 'prune_expired'` for both.

- [ ] **Step 3: Implement `prune_expired` in dead_letter.py**

In `src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/dead_letter.py`:

Change the imports from:
```python
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func, select, text
```
to:
```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, Integer, String, Text, delete, func, select, text
```
Add this function (e.g. after `record_failure`):
```python
def prune_expired(session: Session, retention_days: int) -> int:
    """Delete dead-letter rows older than retention_days; returns the number deleted.

    Run periodically (tasks/retention.py). Terminal-failure rows may hold PII in args_json,
    so they must not accumulate forever — override BaseTask.dlq_args_json to redact at write.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = session.execute(delete(DeadLetterTask).where(DeadLetterTask.failed_at < cutoff))
    session.commit()
    return result.rowcount
```

- [ ] **Step 4: Implement `prune_expired` in inbox.py**

In `src/{{package_name}}/{% if "webhooks" in batteries %}webhooks{% endif %}/inbox.py`, change the head from:
```python
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import WebhookEvent
```
to:
```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .models import WebhookEvent
```
Add after `record`:
```python
def prune_expired(session: Session, retention_days: int) -> int:
    """Delete inbox dedup rows older than retention_days; returns the number deleted.

    Keep retention_days >= your provider's redelivery window: pruning a key lets a later
    redelivery of that event be processed again.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = session.execute(delete(WebhookEvent).where(WebhookEvent.received_at < cutoff))
    session.commit()
    return result.rowcount
```

- [ ] **Step 5: Mirror + run to verify both pass**

```bash
cp "src/framework_cli/template/src/{{package_name}}/{% if \"workers\" in batteries %}tasks{% endif %}/dead_letter.py" /tmp/dq-work/src/demo/tasks/dead_letter.py
cp "src/framework_cli/template/src/{{package_name}}/{% if \"webhooks\" in batteries %}webhooks{% endif %}/inbox.py" /tmp/dq-work/src/demo/webhooks/inbox.py
(cd /tmp/dq-work && uv run pytest tests/unit/test_dlq_retention.py tests/unit/test_webhook_inbox_retention.py -q)
```
Expected: PASS (2 passed).

- [ ] **Step 6: Format check + commit**

```bash
rm -rf /tmp/dq-render && uv run framework template-render --out /tmp/dq-render >/dev/null
(cd /tmp/dq-render && uv run ruff format --check src/demo/tasks/dead_letter.py src/demo/webhooks/inbox.py src/demo/config/settings.py tests/unit/test_dlq_retention.py tests/unit/test_webhook_inbox_retention.py)
```
Expected: `... already formatted`. Then update CLAUDE.md (brief) and commit the 5 files:
```bash
git add CLAUDE.md \
  "src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja" \
  "src/framework_cli/template/src/{{package_name}}/{% if \"workers\" in batteries %}tasks{% endif %}/dead_letter.py" \
  "src/framework_cli/template/src/{{package_name}}/{% if \"webhooks\" in batteries %}webhooks{% endif %}/inbox.py" \
  "src/framework_cli/template/tests/unit/{{ 'test_dlq_retention.py' if 'workers' in batteries else '' }}.jinja" \
  "src/framework_cli/template/tests/unit/{{ 'test_webhook_inbox_retention.py' if 'webhooks' in batteries else '' }}.jinja"
git commit -m "feat(template): DLQ + webhook-inbox retention (prune_expired + config knobs)"
```

---

## Task 2: Retention beat task + schedule wiring

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/retention.py.jinja`
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/schedule.py.jinja`
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/app.py.jinja`
- Modify: `tests/unit/{{ 'test_dlq_retention.py' if 'workers' in batteries else '' }}.jinja` (add the schedule-wiring test)

- [ ] **Step 1: Write the failing schedule-wiring test**

Append to `tests/unit/{{ 'test_dlq_retention.py' if 'workers' in batteries else '' }}.jinja`:
```python
def test_retention_task_is_scheduled_daily():
    from celery import Celery

    from {{ package_name }}.tasks.schedule import register_schedule

    app = Celery()
    register_schedule(app)
    entry = app.conf.beat_schedule["prune-expired-records"]
    assert entry["task"] == "{{ package_name }}.tasks.retention.prune_expired_records"
    assert entry["schedule"] == 86400.0
```
Mirror + run:
```bash
rm -rf /tmp/dq-render && uv run framework template-render --out /tmp/dq-render >/dev/null
cp /tmp/dq-render/tests/unit/test_dlq_retention.py /tmp/dq-work/tests/unit/test_dlq_retention.py
(cd /tmp/dq-work && uv run pytest tests/unit/test_dlq_retention.py::test_retention_task_is_scheduled_daily -q)
```
Expected: FAIL — `KeyError: 'prune-expired-records'` (not in the beat schedule yet).

- [ ] **Step 2: Create the retention task**

Create `src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/retention.py.jinja`:
```python
"""Periodic retention: prune dead-letter rows (and, with webhooks, inbox dedup rows) past
their configured window. Scheduled daily in schedule.py. Deliberately NOT a BaseTask — a
pruning slip is operational, not work to dead-letter."""

from __future__ import annotations

from ..config.settings import get_settings
from ..db.engine import SessionLocal
from ..logging_config import get_logger
from . import dead_letter
from .app import app


@app.task
def prune_expired_records() -> None:
    settings = get_settings()
    log = get_logger()
    with SessionLocal() as session:
        deleted = dead_letter.prune_expired(session, settings.dlq_retention_days)
    log.info("dlq_pruned", deleted=deleted, retention_days=settings.dlq_retention_days)
{%- if "webhooks" in batteries %}

    from ..webhooks import inbox

    with SessionLocal() as session:
        deleted = inbox.prune_expired(session, settings.webhook_inbox_retention_days)
    log.info(
        "webhook_inbox_pruned",
        deleted=deleted,
        retention_days=settings.webhook_inbox_retention_days,
    )
{%- endif %}
```

- [ ] **Step 3: Register the schedule**

In `schedule.py.jinja`, add to the `beat_schedule` dict (after the `worker-heartbeat` entry):
```python
        "prune-expired-records": {
            "task": "{{ package_name }}.tasks.retention.prune_expired_records",
            "schedule": 86400.0,  # daily
        },
```

- [ ] **Step 4: Register the task module on the Celery app**

In `app.py.jinja`, change:
```python
    include=["{{ package_name }}.tasks.tasks"],
```
to:
```python
    include=["{{ package_name }}.tasks.tasks", "{{ package_name }}.tasks.retention"],
```

- [ ] **Step 5: Mirror + run (schedule test + the worker can import retention)**

```bash
rm -rf /tmp/dq-render && uv run framework template-render --out /tmp/dq-render >/dev/null
cp /tmp/dq-render/src/demo/tasks/retention.py /tmp/dq-work/src/demo/tasks/retention.py
cp /tmp/dq-render/src/demo/tasks/schedule.py /tmp/dq-work/src/demo/tasks/schedule.py
cp /tmp/dq-render/src/demo/tasks/app.py /tmp/dq-work/src/demo/tasks/app.py
cp /tmp/dq-render/tests/unit/test_dlq_retention.py /tmp/dq-work/tests/unit/test_dlq_retention.py
(cd /tmp/dq-work && uv run pytest tests/unit/test_dlq_retention.py -q && uv run python -c "import demo.tasks.retention; print('retention importable; task =', demo.tasks.retention.prune_expired_records.name)")
```
Expected: tests PASS; the import prints the task name `demo.tasks.retention.prune_expired_records` (proves the worker registers it).

- [ ] **Step 6: Format check + commit**

```bash
(cd /tmp/dq-render && uv run ruff format --check src/demo/tasks/retention.py src/demo/tasks/schedule.py src/demo/tasks/app.py tests/unit/test_dlq_retention.py)
```
Then update CLAUDE.md (brief) and commit:
```bash
git add CLAUDE.md \
  "src/framework_cli/template/src/{{package_name}}/{% if \"workers\" in batteries %}tasks{% endif %}/retention.py.jinja" \
  "src/framework_cli/template/src/{{package_name}}/{% if \"workers\" in batteries %}tasks{% endif %}/schedule.py.jinja" \
  "src/framework_cli/template/src/{{package_name}}/{% if \"workers\" in batteries %}tasks{% endif %}/app.py.jinja" \
  "src/framework_cli/template/tests/unit/{{ 'test_dlq_retention.py' if 'workers' in batteries else '' }}.jinja"
git commit -m "feat(template): daily prune_expired_records beat task + schedule/registration"
```

---

## Task 3: DLQ redaction seam

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/base.py`
- Create: `src/framework_cli/template/tests/unit/{{ 'test_dlq_redaction.py' if 'workers' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/{{ 'test_dlq_redaction.py' if 'workers' in batteries else '' }}.jinja`:
```python
"""The DLQ args serialization is an overridable seam for redacting PII (hermetic)."""

import json

from {{ package_name }}.tasks.base import BaseTask


def test_dlq_args_json_default_serializes_all_args():
    assert json.loads(BaseTask().dlq_args_json((1, "x"), {})) == [1, "x"]


def test_dlq_args_json_can_be_overridden_to_redact():
    class Redacting(BaseTask):
        def dlq_args_json(self, args, kwargs):
            return json.dumps(["<redacted>"])

    assert json.loads(Redacting().dlq_args_json(({"email": "a@b.c"},), {})) == ["<redacted>"]
```
Mirror + run:
```bash
rm -rf /tmp/dq-render && uv run framework template-render --out /tmp/dq-render >/dev/null
cp /tmp/dq-render/tests/unit/test_dlq_redaction.py /tmp/dq-work/tests/unit/test_dlq_redaction.py
(cd /tmp/dq-work && uv run pytest tests/unit/test_dlq_redaction.py -q)
```
Expected: FAIL — `AttributeError: 'BaseTask' object has no attribute 'dlq_args_json'`.

- [ ] **Step 2: Add the seam to base.py**

In `src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/base.py`, add this method to `BaseTask` (e.g. directly above `on_failure`):
```python
    def dlq_args_json(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        """Serialize task args for the dead-letter row. OVERRIDE to redact PII before it is
        persisted to dead_letter_tasks.args_json (e.g. drop or scrub sensitive fields)."""
        return json.dumps(list(args), default=str)
```
And in `on_failure`, change:
```python
                args_json=json.dumps(list(args), default=str),
```
to:
```python
                args_json=self.dlq_args_json(args, kwargs),
```

- [ ] **Step 3: Mirror + run to verify it passes**

```bash
cp "src/framework_cli/template/src/{{package_name}}/{% if \"workers\" in batteries %}tasks{% endif %}/base.py" /tmp/dq-work/src/demo/tasks/base.py
cp /tmp/dq-render/tests/unit/test_dlq_redaction.py /tmp/dq-work/tests/unit/test_dlq_redaction.py
(cd /tmp/dq-work && uv run pytest tests/unit/test_dlq_redaction.py -q)
```
Expected: PASS (2 passed).

- [ ] **Step 4: Format check + commit**

```bash
rm -rf /tmp/dq-render && uv run framework template-render --out /tmp/dq-render >/dev/null
(cd /tmp/dq-render && uv run ruff format --check src/demo/tasks/base.py tests/unit/test_dlq_redaction.py)
```
Then CLAUDE.md (brief) + commit:
```bash
git add CLAUDE.md \
  "src/framework_cli/template/src/{{package_name}}/{% if \"workers\" in batteries %}tasks{% endif %}/base.py" \
  "src/framework_cli/template/tests/unit/{{ 'test_dlq_redaction.py' if 'workers' in batteries else '' }}.jinja"
git commit -m "feat(template): overridable BaseTask.dlq_args_json redaction seam"
```

---

## Task 4: Docs + whole-slice verification

**Files:**
- Modify: `src/framework_cli/template/README.md.jinja`

- [ ] **Step 1: Document the knobs + seam in the README**

In `README.md.jinja`, find the workers/webhooks-related section (search for "workers" or the DLQ/webhook mention). Add a short note (adapt placement to the existing structure), gated so it only renders with the relevant battery — e.g. inside an existing `{%- if "workers" in batteries %}` doc block, or as a new gated bullet near the endpoints/observability notes:
```jinja
{%- if "workers" in batteries %}
- **Retention:** dead-letter rows are pruned after `APP_DLQ_RETENTION_DAYS` (default 30){% if "webhooks" in batteries %} and webhook-inbox dedup rows after `APP_WEBHOOK_INBOX_RETENTION_DAYS` (default 7; keep ≥ your provider's redelivery window){% endif %} by the daily `prune_expired_records` task. DLQ args may contain PII — override `BaseTask.dlq_args_json` to redact before dead-lettering.
{%- endif %}
```
(If a cleaner spot exists in the README's structure, use it — the requirement is one rendered line covering the two env vars + the redaction seam, battery-gated.)

- [ ] **Step 2: Eval-fixture safety scan**

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
Expected: `broken: 0`. (My settings additions are inside the workers/webhooks jinja blocks, and the `security` fixtures render `batteries: []`, so they should be unaffected. If any DO break — likely a workers/webhooks-battery fixture touching `settings.py`/`base.py`/`app.py` — re-anchor it the way prior slices did: render the fixture's battery set, `patch -p1 --fuzz=3` the change.patch, regenerate via `git diff`, verify `git apply --check`, and commit with `test(eval): re-anchor …`.)

- [ ] **Step 3: Full framework gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run mypy src
```
Expected: all pass, ruff clean, mypy clean.

- [ ] **Step 4: Commit docs + clean up**

```bash
git add CLAUDE.md "src/framework_cli/template/README.md.jinja"
git commit -m "docs(template): note DLQ/inbox retention env vars + dlq_args_json redaction seam"
rm -rf /tmp/dq-work /tmp/dq-render 2>/dev/null
rm -rf /tmp/pytest-of-chris/* 2>/dev/null
```

---

## Notes for the implementer

- **Defaults preserve behavior.** `dlq_args_json` default == the old inline `json.dumps(list(args), default=str)`; retention only *adds* a pruning task. Existing webhook/worker tests must stay green.
- **`result.rowcount`** is populated for a SQLAlchemy Core `delete()` on both SQLite and Postgres — that's the deleted count to return.
- **Cross-battery gating:** `retention.py` always prunes the DLQ (workers); the inbox prune block is jinja-gated on `webhooks` (and imports `..webhooks.inbox` lazily inside that block). A workers-only project prunes just the DLQ.
- **tz-aware test timestamps:** insert `failed_at`/`received_at` as `datetime.now(UTC) - timedelta(...)` so the SQLite comparison matches the tz-aware cutoff.
- **Inbox semantics:** pruning a dedup key re-opens that event to reprocessing — the default (7d) + the settings comment must make the ≥-redelivery-window constraint explicit.
