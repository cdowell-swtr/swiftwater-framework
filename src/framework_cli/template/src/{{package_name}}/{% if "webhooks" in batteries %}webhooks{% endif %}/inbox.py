"""The transactional inbox: dedup by inserting a row keyed on the webhook's idempotency key."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .models import WebhookEvent


def record(session: Session, key: str) -> None:
    """Insert the inbox row; flush so the UNIQUE constraint fires now (duplicate → IntegrityError)."""
    session.add(WebhookEvent(idempotency_key=key))
    session.flush()


def prune_expired(session: Session, retention_days: int) -> int:
    """Delete inbox dedup rows older than retention_days; returns the number deleted.

    Keep retention_days >= your provider's redelivery window: pruning a key lets a later
    redelivery of that event be processed again.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = session.execute(
        delete(WebhookEvent).where(WebhookEvent.received_at < cutoff)
    )
    session.commit()
    return result.rowcount
