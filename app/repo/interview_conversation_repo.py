"""Repository for interview conversation persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.domain.models.interview_conversation import (
    InterviewChannelMap,
    InterviewConversation,
    InterviewConversationStatus,
)


class InterviewConversationRepository:
    """Database access wrapper for interview conversations."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.interview_conversations

    async def create(
        self,
        *,
        conversation_id: str,
        user_id: str,
        channel_map: InterviewChannelMap | dict[str, str],
        organization_id: str | None = None,
        status: InterviewConversationStatus = InterviewConversationStatus.ACTIVE,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> InterviewConversation:
        """Create or return an interview conversation record."""
        started = started_at or datetime.now(timezone.utc)
        normalized_channel_map = self._normalize_channel_map(channel_map)
        document = {
            "_id": conversation_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "organization_id": organization_id,
            "channel_map": normalized_channel_map.model_dump(by_alias=True),
            "status": status.value,
            "started_at": started,
            "ended_at": ended_at,
        }

        result = await self.collection.find_one_and_update(
            {"conversation_id": conversation_id},
            {"$setOnInsert": document},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return InterviewConversation(**result)

    async def get_by_conversation_id(
        self,
        *,
        conversation_id: str,
        organization_id: str | None = None,
    ) -> InterviewConversation | None:
        """Get an interview conversation by its stable conversation id."""
        query: dict[str, str | None] = {"conversation_id": conversation_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        document = await self.collection.find_one(query)
        if document is None:
            return None
        return InterviewConversation(**document)

    @staticmethod
    def _normalize_channel_map(
        channel_map: InterviewChannelMap | dict[str, str],
    ) -> InterviewChannelMap:
        if isinstance(channel_map, InterviewChannelMap):
            return channel_map
        return InterviewChannelMap.model_validate(channel_map)
