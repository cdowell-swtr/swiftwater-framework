"""Minimal WebSocket connection registry."""

from __future__ import annotations

from fastapi import WebSocket

from .metrics import ws_metrics


class ConnectionManager:
    def __init__(self) -> None:
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.append(ws)
        ws_metrics.connection_opened()

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._active:
            self._active.remove(ws)
            ws_metrics.connection_closed()

    async def broadcast(self, message: str) -> None:
        for ws in list(self._active):
            await ws.send_text(message)
            ws_metrics.message_sent()
