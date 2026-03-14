"""Redis-backed storage for stable interview context."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.asyncio import Redis

from app.common.exceptions import RedisContextReadError, RedisContextWriteError
from app.domain.schemas.stt import STTChannelMap, STTChannelIndex, STTSpeakerRole


class StableInterviewContextUtterance(BaseModel):
    """Redis value shape for one closed stable interview utterance."""

    model_config = ConfigDict(extra="forbid")

    utterance_id: str = Field(..., min_length=1, max_length=128)
    conversation_id: str = Field(..., min_length=1, max_length=128)
    source: STTSpeakerRole
    channel: STTChannelIndex
    text: str = Field(..., min_length=1)
    started_at: datetime
    ended_at: datetime
    turn_closed_at: datetime


class InterviewContextMetadata(BaseModel):
    """Stable interview metadata stored alongside recent utterances."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., min_length=1, max_length=128)
    channel_map: STTChannelMap


class RedisInterviewContextStore:
    """Wrap Redis access for recent stable interview context."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        max_recent_utterances: int = 20,
    ) -> None:
        self.redis = redis_client
        self.max_recent_utterances = max_recent_utterances

    async def append_closed_utterance(
        self,
        utterance: StableInterviewContextUtterance,
        *,
        channel_map: STTChannelMap | None = None,
    ) -> StableInterviewContextUtterance:
        """Append one closed stable utterance and trim the recent Redis window."""
        pipeline = self.redis.pipeline(transaction=True)
        key = self.recent_utterances_key(utterance.conversation_id)
        payload = utterance.model_dump_json(by_alias=True)

        try:
            pipeline.rpush(key, payload)
            pipeline.ltrim(key, -self.max_recent_utterances, -1)
            if channel_map is not None:
                metadata = InterviewContextMetadata(
                    conversation_id=utterance.conversation_id,
                    channel_map=channel_map,
                )
                pipeline.set(
                    self.metadata_key(utterance.conversation_id),
                    metadata.model_dump_json(by_alias=True),
                )
            await pipeline.execute()
        except Exception as exc:
            raise RedisContextWriteError(
                "Failed to append stable interview utterance to Redis context"
            ) from exc

        return utterance

    async def get_recent_utterances(
        self,
        *,
        conversation_id: str,
        limit: int | None = None,
    ) -> list[StableInterviewContextUtterance]:
        """Load a bounded recent stable utterance window in timeline order."""
        requested_limit = limit or self.max_recent_utterances
        start = -requested_limit

        try:
            raw_items = await self.redis.lrange(
                self.recent_utterances_key(conversation_id),
                start,
                -1,
            )
        except Exception as exc:
            raise RedisContextReadError(
                "Failed to load stable interview utterances from Redis"
            ) from exc

        return [self._parse_utterance(raw_item) for raw_item in raw_items]

    async def store_conversation_metadata(
        self,
        *,
        conversation_id: str,
        channel_map: STTChannelMap,
    ) -> InterviewContextMetadata:
        """Store stable interview conversation metadata in Redis."""
        metadata = InterviewContextMetadata(
            conversation_id=conversation_id,
            channel_map=channel_map,
        )
        try:
            await self.redis.set(
                self.metadata_key(conversation_id),
                metadata.model_dump_json(by_alias=True),
            )
        except Exception as exc:
            raise RedisContextWriteError(
                "Failed to store interview conversation metadata in Redis"
            ) from exc
        return metadata

    async def get_conversation_metadata(
        self,
        *,
        conversation_id: str,
    ) -> InterviewContextMetadata | None:
        """Load stable interview conversation metadata from Redis."""
        try:
            raw_value = await self.redis.get(self.metadata_key(conversation_id))
        except Exception as exc:
            raise RedisContextReadError(
                "Failed to load interview conversation metadata from Redis"
            ) from exc

        if raw_value is None:
            return None
        return self._parse_metadata(raw_value)

    @staticmethod
    def recent_utterances_key(conversation_id: str) -> str:
        """Build the Redis key for recent stable utterances."""
        return f"conv:{conversation_id}:recent_utterances"

    @staticmethod
    def metadata_key(conversation_id: str) -> str:
        """Build the Redis key for stable conversation metadata."""
        return f"conv:{conversation_id}:metadata"

    @staticmethod
    def _parse_utterance(raw_value: str) -> StableInterviewContextUtterance:
        try:
            payload = json.loads(raw_value)
            return StableInterviewContextUtterance.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RedisContextReadError(
                "Redis stored interview utterance context in an invalid format"
            ) from exc

    @staticmethod
    def _parse_metadata(raw_value: str) -> InterviewContextMetadata:
        try:
            payload = json.loads(raw_value)
            return InterviewContextMetadata.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RedisContextReadError(
                "Redis stored interview conversation metadata in an invalid format"
            ) from exc
