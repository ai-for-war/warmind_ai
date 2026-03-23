"""Repository for meeting transcript session persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING, ReturnDocument

from app.domain.models.meeting import Meeting, MeetingStatus


class MeetingRepository:
    """Database access wrapper for durable meeting sessions."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.meetings

    async def create(
        self,
        *,
        organization_id: str,
        created_by: str,
        stream_id: str,
        title: str | None = None,
        source: str = "google_meet",
        status: MeetingStatus | str = MeetingStatus.STREAMING,
        language: str | None = None,
        meeting_id: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        error_message: str | None = None,
    ) -> Meeting:
        """Create or return a durable meeting session record."""
        document = {
            "_id": meeting_id or uuid4().hex,
            "organization_id": organization_id,
            "created_by": created_by,
            "title": title,
            "source": self._normalize_source(source),
            "status": self._normalize_status(status),
            "language": language,
            "stream_id": stream_id,
            "started_at": started_at or datetime.now(timezone.utc),
            "ended_at": ended_at,
            "error_message": error_message,
        }
        persisted = await self.collection.find_one_and_update(
            {"_id": document["_id"]},
            {"$setOnInsert": document},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return Meeting(**persisted)

    async def get_by_id(self, *, meeting_id: str) -> Meeting | None:
        """Get a meeting session by its durable id."""
        document = await self.collection.find_one({"_id": meeting_id})
        if document is None:
            return None
        return Meeting(**document)

    async def get_by_stream_id(
        self,
        *,
        stream_id: str,
        organization_id: str | None = None,
    ) -> Meeting | None:
        """Get the most recent meeting session for a provider stream id."""
        query: dict[str, str] = {"stream_id": stream_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        document = await self.collection.find_one(query)
        if document is None:
            return None
        return Meeting(**document)

    async def list_by_organization(
        self,
        *,
        organization_id: str,
        limit: int = 50,
    ) -> list[Meeting]:
        """List recent meetings for one organization."""
        cursor = (
            self.collection.find({"organization_id": organization_id})
            .sort([("started_at", DESCENDING)])
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [Meeting(**document) for document in documents]

    async def list_by_creator(
        self,
        *,
        created_by: str,
        organization_id: str,
        limit: int = 50,
    ) -> list[Meeting]:
        """List recent meetings created by one user within an organization."""
        cursor = (
            self.collection.find(
                {
                    "created_by": created_by,
                    "organization_id": organization_id,
                }
            )
            .sort([("started_at", DESCENDING)])
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [Meeting(**document) for document in documents]

    async def list_by_status(
        self,
        *,
        status: MeetingStatus | str,
        limit: int = 50,
    ) -> list[Meeting]:
        """List recent meetings by durable lifecycle state."""
        cursor = (
            self.collection.find({"status": self._normalize_status(status)})
            .sort([("started_at", DESCENDING)])
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [Meeting(**document) for document in documents]

    async def update_status(
        self,
        *,
        meeting_id: str,
        status: MeetingStatus | str,
        ended_at: datetime | None = None,
        error_message: str | None = None,
    ) -> Meeting | None:
        """Update the durable lifecycle state of a meeting session."""
        update_fields: dict[str, object | None] = {
            "status": self._normalize_status(status),
        }
        if ended_at is not None:
            update_fields["ended_at"] = ended_at
        if error_message is not None:
            update_fields["error_message"] = error_message

        document = await self.collection.find_one_and_update(
            {"_id": meeting_id},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return Meeting(**document)

    @staticmethod
    def _normalize_status(status: MeetingStatus | str) -> str:
        if isinstance(status, MeetingStatus):
            return status.value
        return status

    @staticmethod
    def _normalize_source(source: str) -> str:
        normalized = source.strip().lower()
        return normalized or "google_meet"
