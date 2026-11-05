"""
Sortyx 2.0 — WebSocket Connection Manager.

Broadcasting real-time system states, bin fill levels, and sensor readings
to connected frontend client(s).
"""

from __future__ import annotations

import json
from typing import List, Set
from fastapi import WebSocket, WebSocketDisconnect

from app.core.logging_config import get_logger
from app.schemas.websocket import WSMessage

logger = get_logger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept connection and add to active list."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("WebSocket client connected. Total connections: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove connection from active list."""
        self.active_connections.discard(websocket)
        logger.info("WebSocket client disconnected. Total connections: %d", len(self.active_connections))

    async def broadcast_json(self, data: dict) -> None:
        """Broadcast arbitrary JSON dict to all connected clients."""
        dead_connections: List[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception as exc:
                logger.debug("Failed to send WebSocket message: %s", exc)
                dead_connections.append(connection)

        for dead in dead_connections:
            self.active_connections.discard(dead)

    async def broadcast(self, message: WSMessage) -> None:
        """Serialize and broadcast a WSMessage."""
        await self.broadcast_json(message.model_dump(mode="json"))


# Global singleton instance
ws_manager = ConnectionManager()

