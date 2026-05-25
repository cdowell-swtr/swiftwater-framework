"""Process-wide WebSocket metrics — an active-connections gauge + lifecycle/message counters.

A module-level singleton (like observability/recoverability.py / webhooks/metrics.py), updated
by the connection manager + the /ws route and appended to the /metrics exposition. Label-light
by design (no per-connection / per-message-type labels — cardinality).
"""

from __future__ import annotations

import threading


class WebSocketMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._opened = 0
        self._received = 0
        self._sent = 0

    def connection_opened(self) -> None:
        with self._lock:
            self._active += 1
            self._opened += 1

    def connection_closed(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)  # floored — never negative on a double-close

    def message_received(self) -> None:
        with self._lock:
            self._received += 1

    def message_sent(self) -> None:
        with self._lock:
            self._sent += 1

    def render_prometheus(self) -> str:
        with self._lock:
            active, opened, received, sent = self._active, self._opened, self._received, self._sent
        return (
            "# HELP app_websocket_connections_active Currently open WebSocket connections\n"
            "# TYPE app_websocket_connections_active gauge\n"
            f"app_websocket_connections_active {active}\n"
            "# HELP app_websocket_connections_opened_total WebSocket connections accepted\n"
            "# TYPE app_websocket_connections_opened_total counter\n"
            f"app_websocket_connections_opened_total {opened}\n"
            "# HELP app_websocket_messages_received_total Inbound WebSocket messages\n"
            "# TYPE app_websocket_messages_received_total counter\n"
            f"app_websocket_messages_received_total {received}\n"
            "# HELP app_websocket_messages_sent_total Outbound WebSocket messages (broadcast fan-out)\n"
            "# TYPE app_websocket_messages_sent_total counter\n"
            f"app_websocket_messages_sent_total {sent}\n"
        )

    def reset(self) -> None:
        with self._lock:
            self._active = 0
            self._opened = 0
            self._received = 0
            self._sent = 0


ws_metrics = WebSocketMetrics()
"""The process-wide singleton imported by the connection manager, the /ws route, and /metrics."""
