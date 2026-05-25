"""Process-wide GraphQL operation metrics — counts operations by type and outcome.

A module-level singleton (like observability/recoverability.py), incremented by the schema's
MetricsExtension and appended to the /metrics exposition. Label-light by design: operation_type
and outcome are bounded; the client-defined operation NAME is deliberately NOT a label.
"""

from __future__ import annotations

import threading

OPERATION_TYPES = ("query", "mutation", "subscription")
OUTCOMES = ("success", "error")
# 0-initialized base series (subscription is created lazily only if one ever runs).
_BASE = [
    ("query", "success"),
    ("query", "error"),
    ("mutation", "success"),
    ("mutation", "error"),
]

_HEADER = (
    "# HELP app_graphql_operations_total GraphQL operations by type and outcome\n"
    "# TYPE app_graphql_operations_total counter\n"
)


class GraphQLMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str], int] = {k: 0 for k in _BASE}

    def operation(self, operation_type: str, outcome: str) -> None:
        """Increment one (type, outcome) bucket. Unknown values are ignored (never crash a
        request, never create an unbounded series)."""
        if operation_type not in OPERATION_TYPES or outcome not in OUTCOMES:
            return
        with self._lock:
            key = (operation_type, outcome)
            self._counts[key] = self._counts.get(key, 0) + 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                f'app_graphql_operations_total{{operation_type="{t}",outcome="{o}"}} {c}'
                for (t, o), c in sorted(self._counts.items())
            ]
        return _HEADER + "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counts = {k: 0 for k in _BASE}


gql_metrics = GraphQLMetrics()
"""The process-wide singleton imported by the MetricsExtension and the /metrics route."""
