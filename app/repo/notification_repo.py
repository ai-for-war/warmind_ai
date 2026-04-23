"""Repository for notification persistence operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING, ReturnDocument

from app.domain.models.notification import Notification


class NotificationRepository:
    """Database access wrapper for persisted in-app notifications."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.notifications

    async def create(
        self,
        *,
        user_id: str,
        organization_id: str,
        type: str,
        title: str,
        body: str,
        target_type: str,
        target_id: str,
        link: str | None = None,
        actor_id: str | None = None,
        dedupe_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        """Create one unread notification document with sensible defaults."""
        now = datetime.now(timezone.utc)
        payload = Notification(
            user_id=user_id,
            organization_id=organization_id,
            type=type,
            title=title,
            body=body,
            target_type=target_type,
            target_id=target_id,
            link=link,
            actor_id=actor_id,
            dedupe_key=dedupe_key,
            metadata=metadata,
            is_read=False,
            read_at=None,
            created_at=now,
            updated_at=now,
        ).model_dump(by_alias=True, exclude={"id"}, exclude_none=True)
        result = await self.collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)
        return Notification(**payload)

    async def list_by_user_and_organization(
        self,
        *,
        user_id: str,
        organization_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int]:
        """List one caller's notifications ordered newest first."""
        query = {
            "user_id": user_id,
            "organization_id": organization_id,
        }
        skip = (page - 1) * page_size
        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(page_size)
        )
        documents = [document async for document in cursor]
        return (
            [self._to_model(document) for document in documents if document is not None],
            total,
        )

    async def get_unread_count(
        self,
        *,
        user_id: str,
        organization_id: str,
    ) -> int:
        """Return the unread notification count for one caller scope."""
        return await self.collection.count_documents(
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "is_read": False,
            }
        )

    async def find_owned_notification(
        self,
        *,
        notification_id: str,
        user_id: str,
        organization_id: str,
    ) -> Notification | None:
        """Find one owned notification by id and caller scope."""
        object_id = _parse_object_id(notification_id)
        if object_id is None:
            return None

        document = await self.collection.find_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
            }
        )
        return self._to_model(document)

    async def find_by_dedupe_key(
        self,
        *,
        user_id: str,
        organization_id: str,
        dedupe_key: str,
    ) -> Notification | None:
        """Find one logical notification by its dedupe key in caller scope."""
        document = await self.collection.find_one(
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "dedupe_key": dedupe_key,
            }
        )
        return self._to_model(document)

    async def mark_as_read(
        self,
        *,
        notification_id: str,
        user_id: str,
        organization_id: str,
    ) -> Notification | None:
        """Mark one owned notification as read and return the current document."""
        notification = await self.find_owned_notification(
            notification_id=notification_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        if notification is None:
            return None
        if notification.is_read:
            return notification

        now = datetime.now(timezone.utc)
        object_id = _parse_object_id(notification_id)
        if object_id is None:
            return None

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
            },
            {
                "$set": {
                    "is_read": True,
                    "read_at": now,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def mark_all_as_read(
        self,
        *,
        user_id: str,
        organization_id: str,
    ) -> tuple[int, datetime]:
        """Mark all unread notifications as read for one caller scope."""
        now = datetime.now(timezone.utc)
        result = await self.collection.update_many(
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "is_read": False,
            },
            {
                "$set": {
                    "is_read": True,
                    "read_at": now,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count, now

    @staticmethod
    def _to_model(document: dict[str, object] | None) -> Notification | None:
        """Convert one MongoDB document into a typed notification model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return Notification(**payload)


def _parse_object_id(value: str) -> ObjectId | None:
    """Parse one string id into ObjectId when valid."""
    try:
        return ObjectId(value)
    except (TypeError, ValueError, InvalidId):
        return None
