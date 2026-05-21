"""Process-wide recoverability metrics (first-class per the design spec).

A module-level singleton, distinct from the per-app request `MetricsRegistry`, because the
retry decorator and circuit-breaker listener are wired at import time, decoupled from any
FastAPI app instance. The `/metrics` route appends `render_prometheus()` to the per-app
exposition. Deliberately label-light to match the in-process registry's simplicity.
"""

from __future__ import annotations

import threading

_CB_STATE_VALUES = {"closed": 0, "open": 1, "half-open": 2}

_COUNTER_TEMPLATE = (
    "# HELP app_unhandled_exceptions_total Unhandled exceptions caught by the global handler\n"
    "# TYPE app_unhandled_exceptions_total counter\n"
    "app_unhandled_exceptions_total {unhandled}\n"
    "# HELP app_retry_attempts_total Retry attempts scheduled by with_retry\n"
    "# TYPE app_retry_attempts_total counter\n"
    "app_retry_attempts_total {attempts}\n"
    "# HELP app_retries_recovered_total Calls that succeeded after at least one retry\n"
    "# TYPE app_retries_recovered_total counter\n"
    "app_retries_recovered_total {recovered}\n"
    "# HELP app_retries_exhausted_total Calls that exhausted all retries and failed\n"
    "# TYPE app_retries_exhausted_total counter\n"
    "app_retries_exhausted_total {exhausted}\n"
)

_CB_HEADER = (
    "# HELP app_circuit_breaker_state Circuit breaker state (0=closed, 1=open, 2=half-open)\n"
    "# TYPE app_circuit_breaker_state gauge\n"
)


class RecoverabilityMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._unhandled = 0
        self._retry_attempts = 0
        self._retries_recovered = 0
        self._retries_exhausted = 0
        self._cb_states: dict[str, int] = {}

    def record_unhandled_exception(self) -> None:
        with self._lock:
            self._unhandled += 1

    def record_retry_attempt(self) -> None:
        with self._lock:
            self._retry_attempts += 1

    def record_retry_recovered(self) -> None:
        with self._lock:
            self._retries_recovered += 1

    def record_retry_exhausted(self) -> None:
        with self._lock:
            self._retries_exhausted += 1

    def set_circuit_state(self, name: str, state_name: str) -> None:
        with self._lock:
            self._cb_states[name] = _CB_STATE_VALUES[state_name]

    def circuit_state(self, name: str) -> int:
        with self._lock:
            return self._cb_states.get(name, 0)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "unhandled": self._unhandled,
                "retry_attempts": self._retry_attempts,
                "retries_recovered": self._retries_recovered,
                "retries_exhausted": self._retries_exhausted,
            }

    def render_prometheus(self) -> str:
        with self._lock:
            text = _COUNTER_TEMPLATE.format(
                unhandled=self._unhandled,
                attempts=self._retry_attempts,
                recovered=self._retries_recovered,
                exhausted=self._retries_exhausted,
            )
            if self._cb_states:
                text += _CB_HEADER
                for name, value in sorted(self._cb_states.items()):
                    text += f'app_circuit_breaker_state{{name="{name}"}} {value}\n'
            return text

    def reset(self) -> None:
        with self._lock:
            self._unhandled = 0
            self._retry_attempts = 0
            self._retries_recovered = 0
            self._retries_exhausted = 0
            self._cb_states.clear()


recoverability = RecoverabilityMetrics()
"""The process-wide singleton imported by the exception handler, retry decorator, breaker, and /metrics."""
