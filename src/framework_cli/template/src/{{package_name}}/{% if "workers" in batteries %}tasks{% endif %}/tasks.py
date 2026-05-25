"""Your async tasks. `process_async` is the example seam — replace it. `heartbeat` feeds the
worker liveness marker /health reads; keep it.
"""

from __future__ import annotations

import redis

from ..config.settings import get_settings
from . import liveness
from .app import app
from .base import BaseTask


_redis: redis.Redis | None = None


def _redis_client() -> redis.Redis:
    # Cached lazily (one connection pool per worker process, not per task call).
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(get_settings().redis_url)
    return _redis


@app.task(base=BaseTask, bind=True)
def process_async(self, payload: dict) -> None:
    """Example background task. REPLACE with your logic. Failures (after retries) go to the DLQ."""
    # do the slow/heavy work here, off the request path
    return None


# Deliberately NOT on BaseTask: a missed heartbeat is a liveness signal, not work to
# dead-letter — let it fail quietly and recover on the next 30s tick.
@app.task(bind=True)
def heartbeat(self) -> None:
    """Periodic liveness tick (registered in schedule.py). Writes the marker /health checks."""
    liveness.write_heartbeat(_redis_client())  # type: ignore[arg-type]
