"""Conversation repository for database operations."""

import re
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.domain.models.conversation import Conversation, ConversationStatus


class SearchResult(BaseModel):
    """Result from search_by_user containing items and total count."""

    items: list[Conversation]
    total: int


class ConversationRepository:
    """Repository for conversation database operations.

    Implements soft delete pattern - records are marked with deleted_at
    instead of being removed from the database.
    """

    DEFAULT_TITLE = "New Conversation"

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize ConversationRepository with database instance.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        self.collection = db.conversations

    async def create(
        self,
        user_id: str,
        title: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation in database.

        Args:
            user_id: ID of the user creating the conversation
            title: Optional title for the conversation (defaults to "New Conversation")

        Returns:
            Created Conversation instance

        Requirements: 1.1
        """
        now = datetime.now(timezone.utc)
        conversation_data = {
            "user_id": user_id,
            "organization_id": organization_id,
            "title": title or self.DEFAULT_TITLE,
            "status": ConversationStatus.ACTIVE.value,
            "message_count": 0,
            "last_message_at": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }

        result = await self.collection.insert_one(conversation_data)
        conversation_data["_id"] = str(result.inserted_id)

        return Conversation(**conversation_data)

    async def get_by_id(
        self,
        conversation_id: str,
        organization_id: Optional[str] = None,
    ) -> Optional[Conversation]:
        """Get a conversation by ID, excluding soft-deleted records.

        Args:
            conversation_id: Conversation ID to search for

        Returns:
            Conversation instance if found and not deleted, None otherwise

        Requirements: 1.5
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError, InvalidId):
            return None

        query: dict = {
            "_id": object_id,
            "deleted_at": None,
        }
        if organization_id is not None:
            query["organization_id"] = organization_id

        doc = await self.collection.find_one(query)

        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return Conversation(**doc)

    async def get_by_user(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Conversation]:
        """Get conversations for a user with pagination, excluding soft-deleted records.

        Results are ordered by updated_at descending (most recent first).

        Args:
            user_id: User ID to search for
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of Conversation instances belonging to the user

        Requirements: 1.2, 1.6
        """
        query: dict = {
            "user_id": user_id,
            "deleted_at": None,
        }
        if organization_id is not None:
            query["organization_id"] = organization_id

        cursor = (
            self.collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        )

        conversations = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            conversations.append(Conversation(**doc))

        return conversations

    async def search_by_user(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> SearchResult:
        """Search conversations for a user with filters and pagination.

        Args:
            user_id: User ID to search for
            status: Optional status filter (active/archived)
            search: Optional title search (case-insensitive partial match)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            SearchResult with items and total count

        Requirements: 4.1, 4.2, 4.3, 4.4
        """
        # Build query filter
        query: dict = {
            "user_id": user_id,
            "deleted_at": None,
        }
        if organization_id is not None:
            query["organization_id"] = organization_id

        if status is not None:
            query["status"] = status.value

        if search:
            # Case-insensitive regex search with escaped special characters
            query["title"] = {"$regex": re.escape(search), "$options": "i"}

        # Get total count
        total = await self.collection.count_documents(query)

        # Get paginated results sorted by updated_at descending
        cursor = (
            self.collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        )

        items = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(Conversation(**doc))

        return SearchResult(items=items, total=total)

    async def update(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        message_count: Optional[int] = None,
        last_message_at: Optional[datetime] = None,
        organization_id: Optional[str] = None,
    ) -> Optional[Conversation]:
        """Update a conversation's fields.

        Only updates fields that are explicitly provided (not None).
        Always updates the updated_at timestamp.

        Args:
            conversation_id: Conversation ID to update
            title: New title (optional)
            status: New status (optional)
            message_count: New message count (optional)
            last_message_at: New last message timestamp (optional)

        Returns:
            Updated Conversation instance if found and not deleted, None otherwise

        Requirements: 1.3
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError, InvalidId):
            return None

        update_data = {"updated_at": datetime.now(timezone.utc)}

        if title is not None:
            update_data["title"] = title
        if status is not None:
            update_data["status"] = status.value
        if message_count is not None:
            update_data["message_count"] = message_count
        if last_message_at is not None:
            update_data["last_message_at"] = last_message_at

        query: dict = {"_id": object_id, "deleted_at": None}
        if organization_id is not None:
            query["organization_id"] = organization_id

        result = await self.collection.find_one_and_update(
            query,
            {"$set": update_data},
            return_document=True,
        )

        if result is None:
            return None

        result["_id"] = str(result["_id"])
        return Conversation(**result)

    async def soft_delete(
        self,
        conversation_id: str,
        organization_id: Optional[str] = None,
    ) -> bool:
        """Soft delete a conversation by setting deleted_at timestamp.

        The record remains in the database but will be excluded from queries.

        Args:
            conversation_id: Conversation ID to delete

        Returns:
            True if conversation was found and deleted, False otherwise

        Requirements: 1.4
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError, InvalidId):
            return False

        now = datetime.now(timezone.utc)
        query: dict = {"_id": object_id, "deleted_at": None}
        if organization_id is not None:
            query["organization_id"] = organization_id

        result = await self.collection.update_one(
            query,
            {"$set": {"deleted_at": now, "updated_at": now}},
        )

        return result.modified_count > 0

    async def increment_message_count(
        self,
        conversation_id: str,
        last_message_at: Optional[datetime] = None,
        organization_id: Optional[str] = None,
    ) -> Optional[Conversation]:
        """Increment the message count for a conversation.

        Also updates last_message_at and updated_at timestamps.

        Args:
            conversation_id: Conversation ID to update
            last_message_at: Timestamp of the last message (defaults to now)

        Returns:
            Updated Conversation instance if found and not deleted, None otherwise

        Requirements: 2.6 (called by ConversationService)
        """
        try:
            object_id = ObjectId(conversation_id)
        except (TypeError, ValueError, InvalidId):
            return None

        now = datetime.now(timezone.utc)
        message_time = last_message_at or now

        query: dict = {"_id": object_id, "deleted_at": None}
        if organization_id is not None:
            query["organization_id"] = organization_id

        result = await self.collection.find_one_and_update(
            query,
            {
                "$inc": {"message_count": 1},
                "$set": {
                    "last_message_at": message_time,
                    "updated_at": now,
                },
            },
            return_document=True,
        )

        if result is None:
            return None

        result["_id"] = str(result["_id"])
        return Conversation(**result)
