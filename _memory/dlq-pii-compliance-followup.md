---
name: dlq-pii-compliance-followup
description: "DLQ-PII compliance posture — FULLY RESOLVED. Redact-by-default + erasure-scoping + hygiene (FF 8aa1dd6); the last deferral, log-surface scrubbing, shipped in Plan 12 (FF b24806f)."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 61c129b2-5eb7-4302-935f-554fa0cc0686
---

Originated from gate-surfaced concerns on the DLQ during the v0.1.0 release-fix. The
**DLQ-PII compliance-posture slice shipped to `master` (FF `8aa1dd6`, 2026-06-02)** —
spec/plan `docs/superpowers/{specs,plans}/2026-06-02-dlq-pii-compliance-posture*`. Resolved:

- ✅ **Default-redact stance (DECIDED: redact).** `BaseTask.dlq_args_json` default → arg
  types + kwarg count (no values); new `BaseTask.dlq_traceback` default → frame file/line/func
  + exception type, with the message AND source lines redacted. Opt-in to full via overriding
  either seam.
- ✅ **Per-subject GDPR Art-17 erasure → mooted.** Nothing personal is persisted by default,
  so there's no erasure path to build. A new `dead_letter_tasks.redacted` bool column (derived
  in `on_failure` from whether both seams are the framework defaults) tags any opt-in-to-raw
  rows so erasure can be scoped with `WHERE redacted = false`.
- ✅ **Traceback secret exposure** — handled by the `dlq_traceback` redaction above.
- ✅ **Beat-task prune error handling** — `prune_expired_records` wraps each prune in try/except
  → `dlq_prune_failed` / `webhook_inbox_prune_failed`.
- ✅ **Audit attribution** — `triggered_by="prune_expired_records"` on the prune logs.
- ✅ **DEC-0002 retired** (the opt-in-default decision it acknowledged was resolved by the flip).

**LOG-SURFACE SCRUBBING — ✅ RESOLVED in Plan 12 (FF `b24806f`).** Celery's own task-failure
logging (`celery.app.trace`) emitted the raw exception/traceback/args at ERROR → Loki, bypassing
the DLQ-row seams. Fixed NOT by fragile regex but deterministically: a `RedactCeleryFailureFilter`
(`tasks/log_redaction.py`) keyed on Celery's own trace **context dict** blanks the four PII keys
(`exc`/`traceback`/`args`/`kwargs`) while preserving `name`/`id`/`description`; wired onto the
`celery.app.trace` logger via `after_setup_logger`/`after_setup_task_logger` (shared idempotent
instance). Pinned by a Celery eager-mode coupling test (raw `ValueError(...)` → `<redacted>`).
Spec/plan `docs/superpowers/{specs,plans}/2026-06-02-template-hygiene*`. See
[[release-readiness-needs-render-not-local-gate]] / [[template-payload-tdd-loop]] for the
render-loop discipline these template-payload changes used.
