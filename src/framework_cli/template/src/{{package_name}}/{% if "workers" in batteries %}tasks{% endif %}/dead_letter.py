"""The dead-letter queue: tasks that exhausted their retries land here (durable, queryable).

This is the terminal sink Plan 4's `retries_exhausted` recoverability metric anticipated.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..db.base import Base


class DeadLetterTask(Base):
    """One row per task that failed terminally (after retries)."""

    __tablename__ = "dead_letter_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    args_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    traceback: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def record_failure(
    session: Session, *, task_name: str, task_id: str, args_json: str, traceback: str
) -> None:
    """Persist a terminally-failed task. Commits its own transaction (called from on_failure)."""
    session.add(
        DeadLetterTask(
            task_name=task_name, task_id=task_id, args_json=args_json, traceback=traceback
        )
    )
    session.commit()


def count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(DeadLetterTask)) or 0)


def list_recent(session: Session, limit: int = 50) -> list[DeadLetterTask]:
    return list(
        session.scalars(select(DeadLetterTask).order_by(DeadLetterTask.id.desc()).limit(limit))
    )


def render_dlq_metrics(session: Session) -> str:
    """Prometheus exposition for DLQ depth — appended to the app's /metrics (DB is shared truth)."""
    return (
        "# HELP app_dead_letter_tasks Tasks in the dead-letter queue (terminal failures)\n"
        "# TYPE app_dead_letter_tasks gauge\n"
        f"app_dead_letter_tasks {count(session)}\n"
    )
