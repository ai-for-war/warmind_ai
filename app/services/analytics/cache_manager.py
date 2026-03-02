"""Cache manager for analytics data using Redis."""

import hashlib
import json
import logging
from typing import Any, Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class AnalyticsCacheManager:
    """Manages Redis caching for analytics data."""

    CACHE_TTL = 300  # 5 minutes
    KEY_PREFIX = "analytics"

    def __init__(self, redis_client: Redis):
        """
        Initialize cache manager with Redis client.

        Args:
            redis_client: Async Redis client instance.
        """
        self.redis = redis_client

    def _build_key(
        self,
        connection_id: str,
        endpoint: str,
        params: dict,
    ) -> str:
        """
        Build cache key from connection_id, endpoint, and params.

        Args:
            connection_id: The connection ID.
            endpoint: The endpoint name (e.g., 'summary', 'time-series').
            params: Query parameters dict.

        Returns:
            Cache key string in format: analytics:{connection_id}:{endpoint}:{params_hash}
        """
        # Sort keys and serialize to ensure consistent hashing
        params_str = json.dumps(params, sort_keys=True, default=str)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
        return f"{self.KEY_PREFIX}:{connection_id}:{endpoint}:{params_hash}"

    async def get(
        self,
        connection_id: str,
        endpoint: str,
        params: dict,
    ) -> Optional[dict]:
        """
        Get cached data if exists.

        Args:
            connection_id: The connection ID.
            endpoint: The endpoint name.
            params: Query parameters dict.

        Returns:
            Cached data dict or None if not found.
        """
        try:
            key = self._build_key(connection_id, endpoint, params)
            data = await self.redis.get(key)
            if data:
                logger.debug("Cache hit for key: %s", key)
                return json.loads(data)
            logger.debug("Cache miss for key: %s", key)
            return None
        except (ConnectionError, TimeoutError, json.JSONDecodeError) as e:
            logger.warning("Cache get error: %s", e)
            return None

    async def set(
        self,
        connection_id: str,
        endpoint: str,
        params: dict,
        data: Any,
    ) -> None:
        """
        Cache data with TTL.

        Args:
            connection_id: The connection ID.
            endpoint: The endpoint name.
            params: Query parameters dict.
            data: Data to cache (will be JSON serialized).
        """
        try:
            key = self._build_key(connection_id, endpoint, params)
            serialized = json.dumps(data, default=str)
            await self.redis.setex(key, self.CACHE_TTL, serialized)
            logger.debug("Cached data for key: %s", key)
        except (ConnectionError, TimeoutError, TypeError) as e:
            logger.warning("Cache set error: %s", e)

    async def invalidate(self, connection_id: str) -> int:
        """
        Invalidate all cache entries for a connection.

        Args:
            connection_id: The connection ID to invalidate cache for.

        Returns:
            Number of keys deleted.
        """
        try:
            pattern = f"{self.KEY_PREFIX}:{connection_id}:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(
                    "Invalidated %d cache entries for connection %s",
                    deleted,
                    connection_id,
                )
                return deleted
            return 0
        except (ConnectionError, TimeoutError) as e:
            logger.warning("Cache invalidation error: %s", e)
            return 0
