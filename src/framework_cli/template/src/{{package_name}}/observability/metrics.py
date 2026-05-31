"""In-process metrics registry. Fed by the observability middleware; read by /metrics and /health.

A deliberately small, dependency-free store. The latency list is unbounded — fine for low/moderate
traffic, but cap or flush it (e.g. a fixed-size deque or reservoir sample) for high-traffic, long-
running services. Prometheus scrapes /metrics for the fleet-wide view.
"""

from __future__ import annotations

import math
import threading

_PROM_TEMPLATE = (
    "# HELP app_requests_total Total HTTP requests handled\n"
    "# TYPE app_requests_total counter\n"
    "app_requests_total {requests}\n"
    "# HELP app_request_errors_total Total 5xx responses\n"
    "# TYPE app_request_errors_total counter\n"
    "app_request_errors_total {errors}\n"
    "# HELP app_request_latency_p99_ms p99 request latency in milliseconds\n"
    "# TYPE app_request_latency_p99_ms gauge\n"
    "app_request_latency_p99_ms {p99}\n"
    "# HELP app_up Application up indicator\n"
    "# TYPE app_up gauge\n"
    "app_up 1\n"
)


def _p99(latencies: list[float]) -> float:
    """p99 of latencies (the max element for n < 100). Pure; safe to call while holding the lock."""
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    idx = math.ceil(0.99 * len(ordered)) - 1
    return ordered[max(0, idx)]


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latencies_ms: list[float] = []
        self._requests = 0
        self._errors = 0

    def record_request(self, latency_ms: float, status_code: int) -> None:
        with self._lock:
            self._requests += 1
            self._latencies_ms.append(latency_ms)
            if status_code >= 500:
                self._errors += 1

    @property
    def total_requests(self) -> int:
        with self._lock:
            return self._requests

    def error_rate_pct(self) -> float:
        with self._lock:
            if self._requests == 0:
                return 0.0
            return self._errors / self._requests * 100.0

    def p99_latency_ms(self) -> float:
        with self._lock:
            return _p99(self._latencies_ms)

    def render_prometheus(self) -> str:
        with self._lock:
            return _PROM_TEMPLATE.format(
                requests=self._requests,
                errors=self._errors,
                p99=_p99(self._latencies_ms),
            )

    def reset(self) -> None:
        with self._lock:
            self._latencies_ms.clear()
            self._requests = 0
            self._errors = 0
