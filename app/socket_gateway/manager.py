"""Redis manager factory for Socket.IO cross-process communication.

This module provides factory functions to create AsyncRedisManager instances
for both the main server and worker processes. The server manager handles
full bidirectional communication while the worker manager is write-only.
"""

import logging
from typing import Optional

import socketio

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_server_manager: Optional[socketio.AsyncRedisManager] = None
_worker_manager: Optional[socketio.AsyncRedisManager] = None


def get_server_manager() -> Optional[socketio.AsyncRedisManager]:
    """Get AsyncRedisManager for the main server.

    Creates a full AsyncRedisManager that can both publish and subscribe
    to Redis Pub/Sub channels. This is used by the FastAPI server to
    receive events from worker processes.

    Returns:
        AsyncRedisManager instance or None if Redis not configured
    """
    global _server_manager

    if _server_manager is not None:
        return _server_manager

    settings = get_settings()
    redis_url = getattr(settings, "REDIS_URL", None)

    if not redis_url:
        logger.warning("REDIS_URL not configured, using local-only mode")
        return None

    try:
        _server_manager = socketio.AsyncRedisManager(redis_url)
        logger.info("Initialized AsyncRedisManager for server")
        return _server_manager
    except Exception:
        logger.exception("Failed to initialize AsyncRedisManager")
        return None


def get_worker_manager() -> Optional[socketio.AsyncRedisManager]:
    """Get write-only AsyncRedisManager for worker processes.

    Creates an AsyncRedisManager with write_only=True, which can only
    publish events to Redis without accepting client connections.
    This is used by background workers to emit events to clients.

    Returns:
        AsyncRedisManager instance (write_only=True) or None if Redis not configured
    """
    global _worker_manager

    if _worker_manager is not None:
        return _worker_manager

    settings = get_settings()
    redis_url = getattr(settings, "REDIS_URL", None)

    if not redis_url:
        logger.warning("REDIS_URL not configured, worker emit will be skipped")
        return None

    try:
        _worker_manager = socketio.AsyncRedisManager(redis_url, write_only=True)
        logger.info("Initialized write-only AsyncRedisManager for worker")
        return _worker_manager
    except Exception:
        logger.exception("Failed to initialize worker AsyncRedisManager")
        return None
