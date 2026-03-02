"""Write-only Socket Gateway for worker processes.

This module provides a gateway that emits events via Redis Pub/Sub
without requiring a full Socket.IO server. It's designed for use in
background worker processes that need to notify clients about task progress.

Usage:
    from app.socket_gateway.worker_gateway import worker_gateway

    await worker_gateway.emit_to_user(user_id, "event_name", {"key": "value"})
"""

import logging
from typing import Optional

import socketio

from app.socket_gateway.manager import get_worker_manager

logger = logging.getLogger(__name__)


class WorkerSocketGateway:
    """Socket gateway for worker processes using write-only Redis manager.

    This class provides the same emit interface as SocketGateway but uses
    a write-only AsyncRedisManager that publishes events to Redis Pub/Sub
    without accepting client connections.

    The manager is lazily initialized on first use to avoid unnecessary
    Redis connections if emit is never called.
    """

    def __init__(self) -> None:
        """Initialize WorkerSocketGateway with lazy manager initialization."""
        self._manager: Optional[socketio.AsyncRedisManager] = None
        self._initialized: bool = False

    @property
    def manager(self) -> Optional[socketio.AsyncRedisManager]:
        """Lazily initialize and return the Redis manager.

        Returns:
            AsyncRedisManager instance or None if Redis not configured
        """
        if not self._initialized:
            self._manager = get_worker_manager()
            self._initialized = True
        return self._manager

    async def emit_to_user(self, user_id: str, event: str, data: dict) -> None:
        """Emit event to a specific user via their personal room.

        Args:
            user_id: The user's ID
            event: Event name
            data: Event payload data
        """
        if self.manager is None:
            logger.warning("Cannot emit %s: Redis manager not available", event)
            return

        room = f"user:{user_id}"
        try:
            await self.manager.emit(event, data, room=room)
        except Exception:
            logger.exception("Failed to emit %s to user %s", event, user_id)

    async def emit_to_room(self, room: str, event: str, data: dict) -> None:
        """Emit event to all clients in a room.

        Args:
            room: Room name
            event: Event name
            data: Event payload data
        """
        if self.manager is None:
            logger.warning("Cannot emit %s: Redis manager not available", event)
            return

        try:
            await self.manager.emit(event, data, room=room)
        except Exception:
            logger.exception("Failed to emit %s to room %s", event, room)

    async def broadcast(self, event: str, data: dict) -> None:
        """Emit event to all connected clients.

        Args:
            event: Event name
            data: Event payload data
        """
        if self.manager is None:
            logger.warning("Cannot broadcast %s: Redis manager not available", event)
            return

        try:
            await self.manager.emit(event, data)
        except Exception:
            logger.exception("Failed to broadcast %s", event)


# Singleton instance for worker processes
worker_gateway = WorkerSocketGateway()
