"""Socket Gateway module for real-time server-to-client messaging.

This module provides:
- SocketGateway: For use in FastAPI server context
- WorkerSocketGateway: For use in worker processes (via worker_gateway)
"""

import socketio

from app.socket_gateway.server import sio

# ASGI app for mounting with FastAPI
socket_app = socketio.ASGIApp(sio)


class SocketGateway:
    """Public API for emitting events to clients.

    This class provides methods to emit events to specific users,
    rooms, or broadcast to all connected clients.

    Use this in FastAPI server context. For worker processes,
    use worker_gateway from app.socket_gateway.worker_gateway.
    """

    async def emit_to_user(self, user_id: str, event: str, data: dict) -> None:
        """Emit event to a specific user via their personal room.

        Args:
            user_id: The user's ID
            event: Event name
            data: Event payload data
        """
        room = f"user:{user_id}"
        await sio.emit(event, data, room=room)

    async def emit_to_room(self, room: str, event: str, data: dict) -> None:
        """Emit event to all clients in a room.

        Args:
            room: Room name
            event: Event name
            data: Event payload data
        """
        await sio.emit(event, data, room=room)

    async def broadcast(self, event: str, data: dict) -> None:
        """Emit event to all connected clients.

        Args:
            event: Event name
            data: Event payload data
        """
        await sio.emit(event, data)

    async def join_room(self, sid: str, room: str) -> None:
        """Add a connection to a room.

        Args:
            sid: Socket session ID
            room: Room name to join
        """
        await sio.enter_room(sid, room)

    async def leave_room(self, sid: str, room: str) -> None:
        """Remove a connection from a room.

        Args:
            sid: Socket session ID
            room: Room name to leave
        """
        await sio.leave_room(sid, room)


# Singleton instance for use throughout the application
gateway = SocketGateway()
