"""The base task: bounded retry, and on terminal failure a row in the dead-letter queue.

Every task should inherit from BaseTask (the `tasks.py` example does) so failures are captured.
"""

from __future__ import annotations

import json
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

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """Called once retries are exhausted — drain to the dead-letter queue.

        Celery task exhaustion is observed via the DLQ-depth gauge on /metrics, distinct from
        Plan 4's in-process `app_retries_exhausted_total` (which counts tenacity-decorated calls).
        """
        with SessionLocal() as session:
            dead_letter.record_failure(
                session,
                task_name=self.name or "unknown",
                task_id=task_id,
                args_json=json.dumps(list(args), default=str),
                traceback=str(einfo),
            )
