"""The transactional inbox: dedup by inserting a row keyed on the webhook's idempotency key."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import WebhookEvent


def record(session: Session, key: str) -> None:
    """Insert the inbox row; flush so the UNIQUE constraint fires now (duplicate → IntegrityError)."""
    session.add(WebhookEvent(idempotency_key=key))
    session.flush()
