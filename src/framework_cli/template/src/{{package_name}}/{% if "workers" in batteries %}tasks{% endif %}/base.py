"""The base task: bounded retry, and on terminal failure a row in the dead-letter queue.

Every task should inherit from BaseTask (the `tasks.py` example does) so failures are captured.
"""

from __future__ import annotations

import json
import traceback
from typing import Any

import celery

from ..db.engine import SessionLocal
from . import dead_letter


class BaseTask(celery.Task):
    # Bounded retry with exponential backoff + jitter (Plan 4 recoverability discipline).
    # NOTE: autoretry_for=(Exception,) is a broad scaffold default. If you raise Celery's
    # control-flow signals (`self.reject()` / `task.ignore()` — both Exception subclasses),
    # narrow this tuple to your real failure types so they aren't retried + dead-lettered.
    autoretry_for = (Exception,)
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    def dlq_args_json(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        """Default: store the SHAPE of the call (arg types + kwarg count), never the values —
        the dead-letter row carries no personal data. OVERRIDE to serialize full args for a
        task you know carries no PII (you then own the erasure obligation; see dead_letter
        `redacted`)."""
        return json.dumps(
            {"args": [type(a).__name__ for a in args], "kwargs": len(kwargs)}
        )

    def dlq_traceback(self, exc: Exception, einfo: Any) -> str:
        """Default: frame locations (file/line/function) + exception type, source lines and
        exception message redacted (both can carry interpolated PII). OVERRIDE to return
        str(einfo) for a task known PII-free."""
        frames = traceback.extract_tb(exc.__traceback__)
        frame_lines = "".join(
            f'  File "{f.filename}", line {f.lineno}, in {f.name}\n' for f in frames
        )
        return f"{frame_lines}{type(exc).__name__}: <redacted>"

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

        Celery task exhaustion is observed via the DLQ-depth gauge on /metrics, distinct from
        Plan 4's in-process `app_retries_exhausted_total` (which counts tenacity-decorated calls).
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
