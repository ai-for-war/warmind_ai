"""Message repository for database operations."""

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.models.message import (
    Attachment,
    Message,
    MessageMetadata,
    MessageRole,
)


class MessageRepository:
    """Repository for message database operations.

    Implements soft delete pattern - records are marked with deleted_at
    instead of being removed from the database.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize MessageRepository with database instance.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        self.collection = db.messages

    async def create(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        attachments: Optional[list[Attachment]] = None,
        metadata: Optional[MessageMetadata] = None,
        is_complete: bool = True,
    ) -> Message:
        """Create a new message in database.

        Args:
            conversation_id: ID of the conversation this message belongs to
            role: Role of the message sender (user, assistant, system, tool)
            content: Message content text
            attachments: Optional list of attachments (images, files)
            metadata: Optional AI metadata (model, tokens, latency, tool_calls)
            is_complete: Whether the message is complete (False for streaming)

        Returns:
            Created Message instance

        Requirements: 2.1, 2.4, 2.5, 3.1, 3.2
        """
        now = datetime.now(timezone.utc)

        # Convert attachments to dict format for storage
        attachments_data = []
        if attachments:
            attachments_data = [att.model_dump() for att in attachments]

        # Convert metadata to dict format for storage
        metadata_data = None
        if metadata:
            metadata_data = metadata.model_dump(exclude_none=True)

        message_data = {
            "conversation_id": conversation_id,
            "role": role.value if isinstance(role, MessageRole) else role,
            "content": content,
            "attachments": attachments_data,
            "metadata": metadata_data,
            "is_complete": is_complete,
            "created_at": now,
            "deleted_at": None,
        }

        result = await self.collection.insert_one(message_data)
        message_data["_id"] = str(result.inserted_id)

        return Message(**message_data)

    async def get_by_conversation(
        self,
        conversation_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Message]:
        """Get messages for a conversation in chronological order.

        Excludes soft-deleted messages.

        Args:
            conversation_id: Conversation ID to get messages for
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of Message instances in chronological order (oldest first)

        Requirements: 2.2
        """
        cursor = (
            self.collection.find(
                {
                    "conversation_id": conversation_id,
                    "deleted_at": None,
                }
            )
            .sort("created_at", 1)  # Ascending order (oldest first)
            .skip(skip)
            .limit(limit)
        )

        messages = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            messages.append(Message(**doc))

        return messages

    async def get_by_id(self, message_id: str) -> Optional[Message]:
        """Get a message by ID, excluding soft-deleted records.

        Args:
            message_id: Message ID to search for

        Returns:
            Message instance if found and not deleted, None otherwise
        """
        try:
            object_id = ObjectId(message_id)
        except (TypeError, ValueError):
            return None

        doc = await self.collection.find_one(
            {
                "_id": object_id,
                "deleted_at": None,
            }
        )

        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return Message(**doc)

    async def update(
        self,
        message_id: str,
        content: Optional[str] = None,
        metadata: Optional[MessageMetadata] = None,
        is_complete: Optional[bool] = None,
    ) -> Optional[Message]:
        """Update a message's fields.

        Primarily used for streaming support - updating content and is_complete flag.
        Only updates fields that are explicitly provided (not None).

        Args:
            message_id: Message ID to update
            content: New content (optional, for streaming updates)
            metadata: New metadata (optional)
            is_complete: New completion status (optional, for streaming)

        Returns:
            Updated Message instance if found and not deleted, None otherwise

        Requirements: 2.5
        """
        try:
            object_id = ObjectId(message_id)
        except (TypeError, ValueError):
            return None

        update_data = {}

        if content is not None:
            update_data["content"] = content
        if metadata is not None:
            update_data["metadata"] = metadata.model_dump(exclude_none=True)
        if is_complete is not None:
            update_data["is_complete"] = is_complete

        if not update_data:
            # Nothing to update, just return the existing message
            return await self.get_by_id(message_id)

        result = await self.collection.find_one_and_update(
            {"_id": object_id, "deleted_at": None},
            {"$set": update_data},
            return_document=True,
        )

        if result is None:
            return None

        result["_id"] = str(result["_id"])
        return Message(**result)

    async def soft_delete(self, message_id: str) -> bool:
        """Soft delete a message by setting deleted_at timestamp.

        The record remains in the database but will be excluded from queries.

        Args:
            message_id: Message ID to delete

        Returns:
            True if message was found and deleted, False otherwise

        Requirements: 2.3
        """
        try:
            object_id = ObjectId(message_id)
        except (TypeError, ValueError):
            return False

        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"_id": object_id, "deleted_at": None},
            {"$set": {"deleted_at": now}},
        )

        return result.modified_count > 0

    async def soft_delete_by_conversation(self, conversation_id: str) -> int:
        """Soft delete all messages in a conversation.

        Useful when deleting a conversation to also delete its messages.

        Args:
            conversation_id: Conversation ID whose messages should be deleted

        Returns:
            Number of messages that were soft deleted
        """
        now = datetime.now(timezone.utc)
        result = await self.collection.update_many(
            {"conversation_id": conversation_id, "deleted_at": None},
            {"$set": {"deleted_at": now}},
        )

        return result.modified_count
