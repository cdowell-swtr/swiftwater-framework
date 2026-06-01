"""The transactional inbox: dedup by inserting a row keyed on the webhook's idempotency key."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.orm import Session

from ..logging_config import get_logger
from .models import WebhookEvent


def record(session: Session, key: str) -> None:
    """Insert the inbox row; flush so the UNIQUE constraint fires now (duplicate → IntegrityError)."""
    session.add(WebhookEvent(idempotency_key=key))
    session.flush()


def prune_expired(session: Session, retention_days: int) -> int:
    """Delete inbox dedup rows older than retention_days; returns the number deleted.

    Keep retention_days >= your provider's redelivery window: pruning a key lets a later
    redelivery of that event be processed again.

    Commits its own transaction by design: a standalone maintenance prune invoked from the
    prune_expired_records beat task with a dedicated session. retention_days must be
    positive — a value <= 0 yields a now-or-future cutoff that would delete every row.
    """
    if retention_days <= 0:
        raise ValueError("retention_days must be positive")
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = session.execute(
        delete(WebhookEvent).where(WebhookEvent.received_at < cutoff)
    )
    deleted = cast(CursorResult, result).rowcount  # capture before commit
    session.commit()
    get_logger().info(
        "webhook_inbox_pruned", rows_deleted=deleted, retention_days=retention_days
    )
    return deleted
