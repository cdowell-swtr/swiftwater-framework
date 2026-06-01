"""The dead-letter queue: tasks that exhausted their retries land here (durable, queryable).

This is the terminal sink Plan 4's `retries_exhausted` recoverability metric anticipated.
"""

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import (
    CursorResult,
    DateTime,
    Integer,
    String,
    Text,
    delete,
    func,
    select,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..db.base import Base
from ..logging_config import get_logger


class DeadLetterTask(Base):
    """One row per task that failed terminally (after retries)."""

    __tablename__ = "dead_letter_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    args_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'[]'")
    )
    traceback: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def record_failure(
    session: Session, *, task_name: str, task_id: str, args_json: str, traceback: str
) -> None:
    """Persist a terminally-failed task. Commits its own transaction (called from on_failure)."""
    session.add(
        DeadLetterTask(
            task_name=task_name,
            task_id=task_id,
            args_json=args_json,
            traceback=traceback,
        )
    )
    session.commit()


def prune_expired(session: Session, retention_days: int) -> int:
    """Delete dead-letter rows older than retention_days; returns the number deleted.

    Run periodically (tasks/retention.py). Terminal-failure rows may hold PII in args_json,
    so they must not accumulate forever — override BaseTask.dlq_args_json to redact at write.

    Commits its own transaction by design: a standalone maintenance prune invoked from the
    prune_expired_records beat task with a dedicated session, not part of a caller's
    unit-of-work. retention_days must be positive — a value <= 0 yields a now-or-future
    cutoff that would delete every row.
    """
    if retention_days <= 0:
        raise ValueError("retention_days must be positive")
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = session.execute(
        delete(DeadLetterTask).where(DeadLetterTask.failed_at < cutoff)
    )
    deleted = cast(CursorResult, result).rowcount  # capture before commit
    session.commit()
    get_logger().info("dlq_pruned", rows_deleted=deleted, retention_days=retention_days)
    return deleted


def count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(DeadLetterTask)) or 0)


def list_recent(session: Session, limit: int = 50) -> list[DeadLetterTask]:
    return list(
        session.scalars(
            select(DeadLetterTask).order_by(DeadLetterTask.id.desc()).limit(limit)
        )
    )


def render_dlq_metrics(session: Session) -> str:
    """Prometheus exposition for DLQ depth — appended to the app's /metrics (DB is shared truth)."""
    return (
        "# HELP app_dead_letter_tasks Tasks in the dead-letter queue (terminal failures)\n"
        "# TYPE app_dead_letter_tasks gauge\n"
        f"app_dead_letter_tasks {count(session)}\n"
    )
