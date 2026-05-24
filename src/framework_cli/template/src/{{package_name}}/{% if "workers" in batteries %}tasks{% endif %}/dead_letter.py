"""The dead-letter queue: tasks that exhausted their retries land here (durable, queryable).

This is the terminal sink Plan 4's `retries_exhausted` recoverability metric anticipated.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

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
