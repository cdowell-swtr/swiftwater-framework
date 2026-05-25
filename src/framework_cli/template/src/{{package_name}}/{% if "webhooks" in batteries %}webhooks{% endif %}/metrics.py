"""Process-wide webhook ingress metrics — counts inbound webhooks by outcome.

A module-level singleton (like observability/recoverability.py), incremented by the webhook
route and appended to the /metrics exposition. Label-light by design: `outcome` is bounded
(4 values); the provider-defined event type is deliberately NOT a label (cardinality).
"""

from __future__ import annotations

import threading

OUTCOMES = ("accepted", "rejected_signature", "malformed", "duplicate")

_HEADER = (
    "# HELP app_webhooks_received_total Inbound webhooks by processing outcome\n"
    "# TYPE app_webhooks_received_total counter\n"
)


class WebhookMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {o: 0 for o in OUTCOMES}

    def record(self, outcome: str) -> None:
        """Increment one outcome. Unknown outcomes are ignored (never crash the request,
        never create an unbounded series)."""
        with self._lock:
            if outcome in self._counts:
                self._counts[outcome] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                f'app_webhooks_received_total{{outcome="{o}"}} {self._counts[o]}'
                for o in OUTCOMES
            ]
        return _HEADER + "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counts = {o: 0 for o in OUTCOMES}


webhook_metrics = WebhookMetrics()
"""The process-wide singleton imported by routes/webhooks.py and the /metrics route."""
