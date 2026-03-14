"""Redis-backed storage scaffold for stable interview context."""

from redis.asyncio import Redis


class RedisInterviewContextStore:
    """Wrap Redis access for interview conversation context."""

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    @staticmethod
    def recent_utterances_key(conversation_id: str) -> str:
        """Build the Redis key for recent stable utterances."""
        return f"conv:{conversation_id}:recent_utterances"

    @staticmethod
    def metadata_key(conversation_id: str) -> str:
        """Build the Redis key for stable conversation metadata."""
        return f"conv:{conversation_id}:metadata"
