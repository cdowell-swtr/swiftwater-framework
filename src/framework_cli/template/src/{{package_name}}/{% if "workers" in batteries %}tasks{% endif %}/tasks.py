"""Your async tasks. `process_async` is the example seam — replace it. `heartbeat` feeds the
worker liveness marker /health reads; keep it.
"""

from __future__ import annotations

import redis

from ..config.settings import get_settings
from . import liveness
from .app import app
from .base import BaseTask


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


@app.task(base=BaseTask, bind=True)
def process_async(self, payload: dict) -> None:
    """Example background task. REPLACE with your logic. Failures (after retries) go to the DLQ."""
    # do the slow/heavy work here, off the request path
    return None


@app.task(bind=True)
def heartbeat(self) -> None:
    """Periodic liveness tick (registered in schedule.py). Writes the marker /health checks."""
    liveness.write_heartbeat(_redis_client())
