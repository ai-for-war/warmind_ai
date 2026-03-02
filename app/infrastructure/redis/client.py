"""Redis async client connection manager."""

import redis.asyncio as redis
from redis.asyncio import Redis


class RedisClient:
    """Redis connection manager following MongoDB pattern."""

    client: Redis = None

    @classmethod
    async def connect(cls, url: str) -> None:
        """Connect to Redis.

        Args:
            url: Redis connection URL
        """
        cls.client = redis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
        )

    @classmethod
    async def disconnect(cls) -> None:
        """Disconnect from Redis."""
        if cls.client:
            await cls.client.close()
            cls.client = None

    @classmethod
    def get_client(cls) -> Redis:
        """Get Redis client instance.

        Returns:
            Redis client instance

        Raises:
            RuntimeError: If not connected to Redis
        """
        if cls.client is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return cls.client
