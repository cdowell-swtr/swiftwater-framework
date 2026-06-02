# DLQ-PII Compliance Posture — Design Spec

**Date:** 2026-06-02
**Status:** Approved (brainstorm) — not yet planned/implemented
**Scope:** template payload (the `workers` battery's DLQ). Generated-project code, validated via render + the generated project's own tests.
**Related:** the shipped DLQ-PII slice (`367f20d`→`ed63e9f` + v0.1.0 hardening — retention + the `dlq_args_json` seam); the deferred items in `[[dlq-pii-compliance-followup]]`; the decisions-log seed `DEC-0002` (retired by this slice).

---

## 1. Purpose

Make the dead-letter queue **private by default**: a terminally-failed task must not persist personal data unless the builder explicitly opts in. This resolves the compliance-posture question deferred from the v0.1.0 review, in favour of **redact-by-default** (the shipped slice was opt-in-to-redact).

The core rationale: *don't store PII in the first place.* That removes the GDPR Art-17 ("right to be forgotten") erasure path entirely for the default case — there is nothing to erase — which is cheaper and safer than storing PII and building a per-subject deletion mechanism.

## 2. Scope & non-goals

**In scope** (the `workers` battery; `webhooks` where the inbox prune is involved):
- Flip `BaseTask.dlq_args_json` to redact-by-default (structural summary; covers args **and** kwargs).
- New `BaseTask.dlq_traceback` seam, redact-by-default (stack + exception type; message redacted).
- A `redacted` flag column on `dead_letter_tasks` so opt-in-to-raw rows are trivially scoped for erasure.
- Two operational-hygiene items: beat-task prune error handling; `triggered_by` audit attribution.
- Docs: the redact-by-default posture + the erasure-scoping recipe.

**Non-goals (deferred):**
- **Log-surface scrubbing.** Celery's own task-failure logging (and structlog) still emit the *original* exception/traceback to logs. Scrubbing arbitrary log output is broad and fragile; flagged as a **separate follow-up**, not this slice. (The DLQ *row* — what this slice controls — is redacted.)
- **Per-subject erasure mechanism.** Made unnecessary by redact-by-default; only the `redacted=false` scoping recipe is documented.
- **`pyproject`/retention changes** — unchanged from the shipped slice.

## 3. Args redaction — `dlq_args_json` default flip

The default stores the **shape, not the values**, and covers kwargs (closing the current gap where kwargs were ignored):

```python
def dlq_args_json(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Default: store the SHAPE of the call (arg types + kwarg count), never the values —
    so the dead-letter row carries no personal data. OVERRIDE to serialize full args for a
    task you know carries no PII (you then own the erasure obligation; see `redacted` below)."""
    return json.dumps({"args": [type(a).__name__ for a in args], "kwargs": len(kwargs)})
```

Opt-in to full = override returning `json.dumps([list(args), kwargs], default=str)`. Types/counts are not personal data, so the default is PII-safe while still giving a debugging hint about what failed.

## 4. Traceback redaction — new `dlq_traceback` seam

Interpolated PII in a traceback lives in the **exception-message line** (`ValueError: bad <actual_email>`); the stack frames show source *templates* (code), not data. So the default keeps the stack + the exception **type** and redacts the **message**:

```python
def dlq_traceback(self, exc: Exception, einfo: Any) -> str:
    """Default: full stack + exception type, with the message redacted (interpolated PII
    lives in the message). OVERRIDE to return str(einfo) for a task known PII-free."""
    stack = "".join(traceback.format_tb(exc.__traceback__))
    return f"{stack}{type(exc).__name__}: <redacted>"
```

`on_failure` calls `self.dlq_traceback(exc, einfo)` instead of `str(einfo)`.

## 5. The `redacted` flag (erasure scoping)

Add a `redacted: bool` column to `dead_letter_tasks` (default `true`). `on_failure` sets it by detecting whether the task used the framework's safe defaults:

```python
redacted = (
    type(self).dlq_args_json is BaseTask.dlq_args_json
    and type(self).dlq_traceback is BaseTask.dlq_traceback
)
```

- **No overrides** → `redacted=true` → no PII → erasure is a no-op.
- **Either seam overridden** (opt-in to raw, or custom redaction) → `redacted=false` → the builder scopes any erasure request with `WHERE redacted = false AND <subject match>`.

Derived (not a separate builder-set flag) **to remove the footgun**: a builder cannot store raw args while leaving the row tagged safe. It is **conservative** — custom-but-safe redaction also flags `redacted=false`; over-flagging is harmless (erasure reviews the row and finds nothing), under-flagging would not be.

## 6. Operational-hygiene items (folded in)

- **Beat-task prune error handling:** wrap each `prune_expired` call in `prune_expired_records` (`tasks/retention.py`) in try/except that emits a structured `dlq_prune_failed` / `webhook_inbox_prune_failed` error log. A silently-failing prune is itself a retention-compliance gap.
- **Audit attribution:** add `triggered_by="prune_expired_records"` to the `dlq_pruned` / `webhook_inbox_pruned` audit logs emitted by `prune_expired`.

## 7. Migration, upskill, cleanup

- **One additive migration** (`migrations/versions/0004_dlq_redacted_flag` — gated on `workers`): add the `redacted` boolean column, `nullable=False`, `server_default=true` (existing rows treated as redacted — they predate raw storage). `down_revision = 0003_dead_letter`. The reversible `downgrade()` drops the column.
- **No other schema change** — `args_json`/`traceback` columns are unchanged; only their *written content* changes. Upskill 3-way-merges the new `base.py` defaults; a builder's existing `dlq_args_json` override is preserved (and now also flags `redacted=false`, correctly).
- **Retire `DEC-0002`** (`docs/superpowers/decisions/DEC-0002-*.md`): `status: deferred` → `retired`, with a note that redact-by-default replaced the opt-in default, so the compliance finding is resolved (not acknowledged).

## 8. Docs

`README.md.jinja` DLQ section: state that the DLQ stores **no personal data by default** (args = shape only; traceback = stack with message redacted); to store full args/traceback for a PII-free task, override `dlq_args_json` / `dlq_traceback`; *if you do, those rows are `redacted=false` and you own the erasure obligation — scope erasure with `WHERE redacted = false`.* Note log-surface scrubbing as a known follow-up.

## 9. Testing (template-payload TDD loop — render + generated-project tests)

- `dlq_args_json` default → JSON with arg **type names** + kwarg **count**, and **no values** (assert a PII-shaped value does not appear); an overriding subclass → full args+kwargs present.
- `dlq_traceback` default → contains the stack + `<redacted>` and **not** the exception message text; override → full `str(einfo)`.
- `on_failure` sets `redacted=true` for a default `BaseTask` subclass and `redacted=false` for one overriding either seam (hermetic — a fake einfo + in-memory SQLite, matching the existing `test_dlq_redaction.py` pattern).
- Migration `0004` applies + reverses; the column defaults `true`.
- `prune_expired_records` emits `dlq_prune_failed`/`webhook_inbox_prune_failed` when a prune raises; the prune audit logs carry `triggered_by`.

## 10. Self-review

- **No placeholders.** All seams + the flag + the migration are concrete.
- **Consistency:** redact-by-default (§3/§4) + the derived `redacted` flag (§5) + erasure-moot docs (§8) are mutually reinforcing; the flag is the single source of "could this row hold PII?".
- **Scope:** one implementation plan (base.py seams, dead_letter model + migration, retention.py hygiene, README, DEC-0002 retirement, tests). Log-surface scrubbing explicitly out.
- **Ambiguity:** "redact" is defined precisely per surface (args = types+counts; traceback = stack + type, message → `<redacted>`). The flag is derived, not builder-set, to avoid divergence.
