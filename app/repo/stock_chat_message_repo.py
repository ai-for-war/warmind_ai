"""Repository for dedicated stock-chat message persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

from app.domain.models.stock_chat_message import (
    StockChatMessage,
    StockChatMessageRole,
)


class StockChatMessageRepository:
    """Database access wrapper for stock-chat transcript messages."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.stock_chat_messages

    async def create(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
        role: StockChatMessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> StockChatMessage:
        """Create one stock-chat transcript message in the caller's scope."""
        now = datetime.now(timezone.utc)
        payload = StockChatMessage(
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
            role=role,
            content=content,
            metadata=metadata,
            created_at=now,
            deleted_at=None,
        ).model_dump(by_alias=True, exclude={"id"})
        payload["role"] = role.value if isinstance(role, StockChatMessageRole) else role

        result = await self.collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)
        return StockChatMessage(**payload)

    async def get_by_conversation(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[StockChatMessage]:
        """List active messages for one owned stock-chat conversation chronologically."""
        cursor = (
            self.collection.find(
                {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "deleted_at": None,
                }
            )
            .sort([("created_at", ASCENDING), ("_id", ASCENDING)])
            .skip(skip)
            .limit(limit)
        )

        messages: list[StockChatMessage] = []
        async for document in cursor:
            message = self._to_model(document)
            if message is not None:
                messages.append(message)
        return messages

    async def find_owned(
        self,
        *,
        message_id: str,
        user_id: str,
        organization_id: str,
    ) -> StockChatMessage | None:
        """Find one active stock-chat message owned by the caller."""
        object_id = _parse_object_id(message_id)
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

    async def soft_delete_by_conversation(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
    ) -> int:
        """Soft-delete all active messages in one owned stock-chat conversation."""
        now = datetime.now(timezone.utc)
        result = await self.collection.update_many(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "deleted_at": None,
            },
            {"$set": {"deleted_at": now}},
        )
        return result.modified_count

    @staticmethod
    def _to_model(document: dict[str, Any] | None) -> StockChatMessage | None:
        """Convert one MongoDB document into a stock-chat message model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return StockChatMessage(**payload)


def _parse_object_id(value: str) -> ObjectId | None:
    """Parse one string id into ObjectId when valid."""
    try:
        return ObjectId(value)
    except (TypeError, ValueError, InvalidId):
        return None
