"""The builder seam: replace `handle_event` with your webhook logic.

Keep it FAST — this runs inline in the request. Heavy or slow work (external calls, big
writes) belongs behind the `workers` battery (`framework upskill --with workers`); add it
and dispatch from here to a Celery task instead of processing inline.
"""

from __future__ import annotations

from ..logging_config import get_logger


def handle_event(event: dict) -> None:
    """Process a verified, de-duplicated webhook event. REPLACE THIS with your logic."""
    get_logger().info("webhook_event", event_type=event.get("type", "unknown"))
