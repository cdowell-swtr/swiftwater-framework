"""Per-request observability: correlation id, latency timing, metric recording, request log.

Monitoring endpoints (/health, /metrics, /heartbeat) are not recorded so synthetic load
controls the SLO inputs and monitoring traffic does not skew the SLOs.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ..logging_config import correlation_id_var, get_logger

if TYPE_CHECKING:
    from ..observability.metrics import MetricsRegistry

_UNRECORDED_PATHS = frozenset({"/health", "/metrics", "/heartbeat"})
_CORRELATION_HEADER = "X-Correlation-ID"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, metrics: "MetricsRegistry") -> None:
        super().__init__(app)
        self._metrics = metrics
        self._log = get_logger()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cid = request.headers.get(_CORRELATION_HEADER) or uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        request.state.correlation_id = cid
        start = time.perf_counter()
        record = request.url.path not in _UNRECORDED_PATHS
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if record:
                self._metrics.record_request(elapsed_ms, 500)
            self._log.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round(elapsed_ms, 2),
            )
            correlation_id_var.reset(token)
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if record:
            self._metrics.record_request(elapsed_ms, response.status_code)
        self._log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed_ms, 2),
        )
        response.headers[_CORRELATION_HEADER] = cid
        correlation_id_var.reset(token)
        return response
