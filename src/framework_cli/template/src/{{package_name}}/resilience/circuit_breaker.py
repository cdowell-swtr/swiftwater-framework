"""Circuit breaker built on pybreaker.

`build_breaker` returns a named CircuitBreaker whose state transitions are logged and mirrored
into the recoverability metrics gauge (exposed on /metrics). Wrap calls to an unstable
dependency: `breaker.call(fn, *args)` or use `@breaker` as a decorator. When open, calls fail
fast with pybreaker.CircuitBreakerError instead of hammering the failing dependency.
"""

from __future__ import annotations

import pybreaker

from ..logging_config import get_logger
from ..observability.recoverability import recoverability

_log = get_logger()


class _MetricsListener(pybreaker.CircuitBreakerListener):
    """Logs every state transition and updates the recoverability gauge."""

    def __init__(self, name: str) -> None:
        self._name = name

    def state_change(
        self,
        cb: pybreaker.CircuitBreaker,
        old_state: pybreaker.CircuitBreakerState | None,
        new_state: pybreaker.CircuitBreakerState,
    ) -> None:
        recoverability.set_circuit_state(self._name, new_state.name)
        _log.warning(
            "circuit_breaker_state_change",
            breaker=self._name,
            old_state=old_state.name if old_state is not None else "none",
            new_state=new_state.name,
        )


def build_breaker(
    *, name: str = "default", fail_max: int = 5, reset_timeout: float = 30.0
) -> pybreaker.CircuitBreaker:
    breaker = pybreaker.CircuitBreaker(
        fail_max=fail_max,
        reset_timeout=reset_timeout,
        name=name,
        listeners=[_MetricsListener(name)],
    )
    # Seed the gauge: pybreaker fires state_change only on transitions, not at construction.
    recoverability.set_circuit_state(name, "closed")
    return breaker
