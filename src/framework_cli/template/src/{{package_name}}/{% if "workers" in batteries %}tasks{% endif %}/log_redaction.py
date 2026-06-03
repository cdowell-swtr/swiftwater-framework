"""Redact PII from Celery's built-in task-failure logs.

Celery logs terminal failures via the `celery.app.trace` logger, calling
`logger.log(severity, FORMAT, context)` where `context` is a dict that becomes the
LogRecord's `args`. The PII (exception repr, traceback, call args/kwargs) lives in four
known keys. This filter blanks those keys and passes the record through, preserving the
task name/id/description so the failure stays observable. Deterministic — keyed on
Celery's own dict keys, no regex over content, no replacement logger.
"""

from __future__ import annotations

import logging


class RedactCeleryFailureFilter(logging.Filter):
    _PII_KEYS = ("exc", "traceback", "args", "kwargs")

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = record.args
        if (
            isinstance(ctx, dict)
            and "id" in ctx
            and any(k in ctx for k in self._PII_KEYS)
        ):
            record.args = {
                **ctx,
                **{k: "<redacted>" for k in self._PII_KEYS if k in ctx},
            }
        return True  # always pass — we mutate, never drop
