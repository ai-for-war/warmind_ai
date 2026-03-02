"""Redis queue implementation for async task processing."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisQueue:
    """Redis-based message queue for async task processing.

    Uses Redis lists for FIFO queue operations.
    """

    def __init__(self, client: Redis):
        """Initialize RedisQueue with Redis client.

        Args:
            client: Redis client instance
        """
        self._client = client

    async def enqueue(
        self,
        queue_name: str,
        data: dict[str, Any],
    ) -> bool:
        """Add a task to the queue.

        Args:
            queue_name: Name of the queue
            data: Task data to enqueue

        Returns:
            True if enqueued successfully
        """
        try:
            task_data = {
                **data,
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._client.rpush(queue_name, json.dumps(task_data))
            logger.debug("Enqueued task to %s: %s", queue_name, data)
            return True
        except Exception as e:
            logger.error("Failed to enqueue task: %s", e)
            return False

    async def dequeue(
        self,
        queue_name: str,
        timeout: int = 0,
    ) -> Optional[dict[str, Any]]:
        """Remove and return a task from the queue.

        Args:
            queue_name: Name of the queue
            timeout: Blocking timeout in seconds (0 = non-blocking)

        Returns:
            Task data if available, None otherwise
        """
        try:
            if timeout > 0:
                result = await self._client.blpop(queue_name, timeout=timeout)
                if result:
                    _, data = result
                    return json.loads(data)
            else:
                data = await self._client.lpop(queue_name)
                if data:
                    return json.loads(data)
            return None
        except Exception as e:
            logger.error("Failed to dequeue task: %s", e)
            return None

    async def queue_length(self, queue_name: str) -> int:
        """Get the number of tasks in the queue.

        Args:
            queue_name: Name of the queue

        Returns:
            Number of tasks in queue
        """
        try:
            return await self._client.llen(queue_name)
        except Exception as e:
            logger.error("Failed to get queue length: %s", e)
            return 0
