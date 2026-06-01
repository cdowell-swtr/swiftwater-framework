# DLQ / webhook-inbox retention + DLQ redaction seam — design

**Date:** 2026-06-01
**Status:** approved (brainstorm) → ready for implementation plan
**Source findings:** template-audit `template-audit-2026-05-31-76d9b65` (data-lineage 3× high + 2× medium, compliance 2× medium) — the dead-letter queue stores full task args (incl. webhook payloads = potential PII) in `args_json` plain text with no retention, and the webhook inbox grows unbounded. The **last** deferred template-audit slice (the obs-completeness A/B/C bucket is merged).

## Problem

1. **DLQ `args_json` is an unredacted, unbounded PII store.** `BaseTask.on_failure` (`tasks/base.py`) does `json.dumps(list(args), default=str)` on terminal failure. For `process_async.delay(event)` the args are the **full webhook payload**, so personal data lands in `dead_letter_tasks.args_json` in plain text — and nothing ever deletes it.
2. **The webhook inbox grows unbounded.** `webhook_events` (`webhooks/models.py`) stores one row per processed webhook (the `idempotency_key` — a 64-char key, **not** the payload) with no pruning. This is a storage-growth / retention concern (and a minor PII one if keys are PII-derived), not a payload-PII store. Pruning must stay **≥ the provider's redelivery window**, or dedup silently breaks.

The only durable payload store is the DLQ; the live payload otherwise lives transiently in the redis broker until the task completes.

Per the framework's "prescribe config-driven defaults, pre-empt antipatterns" philosophy, this slice ships an **active, config-driven retention** mechanism + a **redaction seam**, rather than leaving retention/redaction entirely to the builder.

## Scope

**In scope**
1. Retention config knobs (`dlq_retention_days`, `webhook_inbox_retention_days`).
2. `prune_expired(session, retention_days)` for the DLQ and the inbox.
3. A daily retention beat task that prunes both (inbox pruning jinja-gated on the webhooks battery).
4. An overridable `BaseTask.dlq_args_json` redaction seam (default = current behavior).
5. Docs (docstrings + a README line).

**Out of scope** — encrypting `args_json` at rest; per-field PII classification/decorators; an audit log of DLQ access (the heavier app-domain medium findings); changing what `process_async` stores by default.

## Design

### Component 1 — config knobs (`config/settings.py.jinja`)

- In the `{%- if "workers" in batteries %}` block: `dlq_retention_days: int = 30` (with a one-line comment: terminal-failure rows pruned after N days).
- In the `{%- if "webhooks" in batteries %}` block: `webhook_inbox_retention_days: int = 7` (comment: keep ≥ your provider's redelivery window, or dedup breaks). Both `APP_`-prefixed (`APP_DLQ_RETENTION_DAYS`, `APP_WEBHOOK_INBOX_RETENTION_DAYS`).

### Component 2 — prune functions

- `tasks/dead_letter.py` → `prune_expired(session: Session, retention_days: int) -> int`: delete `DeadLetterTask` rows where `failed_at < now() - retention_days`; commit; return the deleted count. Use a `delete()` statement with `func.now()` - interval semantics computed in Python (`datetime.now(UTC) - timedelta(days=retention_days)`) compared against the column, so it's DB-portable (SQLite-testable).
- `webhooks/inbox.py` → `prune_expired(session: Session, retention_days: int) -> int`: same against `WebhookEvent.received_at`.

Both: `cutoff = datetime.now(UTC) - timedelta(days=retention_days)`; `session.execute(delete(Model).where(Model.<ts> < cutoff))`; `session.commit()`; return `result.rowcount`.

### Component 3 — retention beat task + schedule

- New `tasks/retention.py`:
  ```python
  @app.task(bind=True)
  def prune_expired_records(self) -> None:
      settings = get_settings()
      with SessionLocal() as session:
          dlq = dead_letter.prune_expired(session, settings.dlq_retention_days)
      log = get_logger()
      log.info("dlq_pruned", deleted=dlq, retention_days=settings.dlq_retention_days)
      {%- if "webhooks" in batteries %}
      with SessionLocal() as session:
          inbox = webhooks.inbox.prune_expired(session, settings.webhook_inbox_retention_days)
      log.info("webhook_inbox_pruned", deleted=inbox, retention_days=settings.webhook_inbox_retention_days)
      {%- endif %}
  ```
  (Exact imports/structure resolved in the plan; NOT on `BaseTask` — a pruning slip is operational, not work to dead-letter, mirroring the `heartbeat` task's "deliberately not BaseTask" note.)
- `schedule.py.jinja` → add to `beat_schedule`:
  ```python
  "prune-expired-records": {
      "task": "{{ package_name }}.tasks.retention.prune_expired_records",
      "schedule": 86400.0,  # daily
  },
  ```
- `tasks/retention.py` must be added to the Celery app's `include=[...]` (in `app.py`) so the worker registers it (alongside `{{ package_name }}.tasks.tasks`).

### Component 4 — DLQ redaction seam (`tasks/base.py`)

Add an overridable method and route `on_failure` through it:
```python
def dlq_args_json(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Serialize task args for the dead-letter row. OVERRIDE to redact PII before it is
    persisted to dead_letter_tasks.args_json (e.g. drop/scrub sensitive fields)."""
    return json.dumps(list(args), default=str)
```
`on_failure` calls `args_json=self.dlq_args_json(args, kwargs)`. Default behavior is byte-identical to today; builders override `dlq_args_json` on their task base/subclass to redact.

### Component 5 — docs

- `dead_letter.py` / `inbox.py` module docstrings: note rows are pruned after `APP_DLQ_RETENTION_DAYS` / `APP_WEBHOOK_INBOX_RETENTION_DAYS` (daily beat task), and that DLQ args may contain PII — override `BaseTask.dlq_args_json` to redact.
- README: one line under the workers/webhooks section pointing at the two retention env vars + the redaction seam.

## Testing (hermetic, rendered-project)

- `tasks/dead_letter.py::prune_expired` (SQLite): insert DLQ rows with explicit `failed_at` (one old, one recent), `prune_expired(session, retention_days=N)`, assert old row deleted + recent kept + returned count == 1.
- `webhooks/inbox.py::prune_expired` (SQLite): same against `WebhookEvent.received_at`.
- redaction seam: a `BaseTask` subclass overriding `dlq_args_json` to redact; assert `dlq_args_json(args, kwargs)` returns the redacted JSON and the default returns the full args JSON. (Hermetic — call the method directly; no DB.)
- retention task wiring: assert `prune_expired_records` is registered (importable + in the beat schedule) — e.g. `register_schedule` populates the `prune-expired-records` entry pointing at the task.

The existing acceptance tier (testcontainers Postgres) still exercises the real DLQ/inbox; these hermetic tests are the fast-tier guard.

## File changes (summary)

| File | Change |
|---|---|
| `src/{{package_name}}/config/settings.py.jinja` | `dlq_retention_days` (workers), `webhook_inbox_retention_days` (webhooks) |
| `src/{{package_name}}/{…tasks…}/dead_letter.py` | `prune_expired` + docstring |
| `src/{{package_name}}/{…webhooks…}/inbox.py` | `prune_expired` + docstring |
| `src/{{package_name}}/{…tasks…}/retention.py` | new — `prune_expired_records` beat task |
| `src/{{package_name}}/{…tasks…}/schedule.py.jinja` | register the daily prune in `beat_schedule` |
| `src/{{package_name}}/{…tasks…}/app.py.jinja` | add `retention` to Celery `include` |
| `src/{{package_name}}/{…tasks…}/base.py` | `dlq_args_json` seam; `on_failure` routes through it |
| `README.md.jinja` | retention env vars + redaction-seam note |
| template `tests/unit/` | prune (×2) + redaction-seam + schedule-wiring tests |

## Risks

- **Inbox pruning vs dedup window** — pruning inbox rows enables re-processing of old events; the default (7d) + the comment must make the ≥-redelivery-window constraint explicit.
- **`delete().where(ts < cutoff)` portability** — compute the cutoff in Python (`datetime.now(UTC) - timedelta`) and compare to the column, so it works on SQLite (tests) and Postgres (prod). Confirm `result.rowcount` is populated for the delete.
- **Task registration** — `tasks/retention.py` must be in the Celery `include` list or the worker won't register `prune_expired_records`; the schedule-wiring test guards the beat entry, and an import in the test guards registration.
- **Format/fixtures** — run `ruff format --check` on rendered output; re-run the per-fixture `git apply --check` scan (the touched files — base.py, settings.py, app.py — may be eval-fixture-anchored; expect to re-anchor if so, like prior slices).
