"""Repository for dedicated stock-chat conversation persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.domain.models.stock_chat_conversation import (
    StockChatConversation,
    StockChatConversationStatus,
)


class StockChatConversationRepository:
    """Database access wrapper for stock-chat conversations."""

    DEFAULT_TITLE = "Stock Chat"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.stock_chat_conversations

    async def create(
        self,
        *,
        user_id: str,
        organization_id: str,
        title: str | None = None,
    ) -> StockChatConversation:
        """Create one stock-chat conversation in the caller's scope."""
        now = datetime.now(timezone.utc)
        payload = StockChatConversation(
            user_id=user_id,
            organization_id=organization_id,
            title=title or self.DEFAULT_TITLE,
            status=StockChatConversationStatus.ACTIVE,
            message_count=0,
            last_message_at=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        ).model_dump(by_alias=True, exclude={"id"})
        payload["status"] = StockChatConversationStatus.ACTIVE.value

        result = await self.collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)
        return StockChatConversation(**payload)

    async def find_owned(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
    ) -> StockChatConversation | None:
        """Find one active stock-chat conversation owned by the caller."""
        object_id = _parse_object_id(conversation_id)
        if object_id is None:
            return None

        document = await self.collection.find_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "deleted_at": None,
            }
        )
        return self._to_model(document)

    async def increment_message_count(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
        last_message_at: datetime | None = None,
    ) -> StockChatConversation | None:
        """Increment message count and update conversation activity timestamps."""
        object_id = _parse_object_id(conversation_id)
        if object_id is None:
            return None

        now = datetime.now(timezone.utc)
        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "deleted_at": None,
            },
            {
                "$inc": {"message_count": 1},
                "$set": {
                    "last_message_at": last_message_at or now,
                    "updated_at": now,
                },
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def soft_delete(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
    ) -> bool:
        """Soft-delete one owned stock-chat conversation."""
        object_id = _parse_object_id(conversation_id)
        if object_id is None:
            return False

        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "deleted_at": None,
            },
            {"$set": {"deleted_at": now, "updated_at": now}},
        )
        return result.modified_count > 0

    @staticmethod
    def _to_model(document: dict[str, Any] | None) -> StockChatConversation | None:
        """Convert one MongoDB document into a stock-chat conversation model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return StockChatConversation(**payload)


def _parse_object_id(value: str) -> ObjectId | None:
    """Parse one string id into ObjectId when valid."""
    try:
        return ObjectId(value)
    except (TypeError, ValueError, InvalidId):
        return None
