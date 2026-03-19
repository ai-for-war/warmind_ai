"""Repository for meeting record persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.domain.models.meeting_record import MeetingRecord, MeetingRecordStatus


class MeetingRecordRepository:
    """Database access wrapper for durable meeting records."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.meeting_records

    async def create(
        self,
        *,
        user_id: str,
        organization_id: str,
        language: str,
        provider: str,
        meeting_id: str | None = None,
        status: MeetingRecordStatus = MeetingRecordStatus.ACTIVE,
        started_at: datetime | None = None,
        stopped_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> MeetingRecord:
        """Create a durable meeting record."""
        now = started_at or datetime.now(timezone.utc)
        record_id = meeting_id or uuid4().hex
        document = {
            "_id": record_id,
            "user_id": user_id,
            "organization_id": organization_id,
            "language": language,
            "status": status.value,
            "provider": provider,
            "started_at": now,
            "updated_at": now,
            "stopped_at": stopped_at,
            "completed_at": completed_at,
            "error_message": error_message,
        }

        await self.collection.insert_one(document)
        return MeetingRecord(**document)

    async def get_by_id(
        self,
        *,
        meeting_id: str,
        organization_id: str | None = None,
    ) -> MeetingRecord | None:
        """Get a meeting record by id, optionally scoped to an organization."""
        query: dict[str, str] = {"_id": meeting_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        document = await self.collection.find_one(query)
        if document is None:
            return None
        return MeetingRecord(**document)

    async def mark_stopping(
        self,
        *,
        meeting_id: str,
        organization_id: str | None = None,
        stopped_at: datetime | None = None,
    ) -> MeetingRecord | None:
        """Mark a meeting record as stopping."""
        return await self._update_record(
            meeting_id=meeting_id,
            organization_id=organization_id,
            updates={
                "status": MeetingRecordStatus.STOPPING.value,
                "stopped_at": stopped_at or datetime.now(timezone.utc),
            },
        )

    async def mark_completed(
        self,
        *,
        meeting_id: str,
        organization_id: str | None = None,
        completed_at: datetime | None = None,
    ) -> MeetingRecord | None:
        """Mark a meeting record as completed."""
        return await self._update_record(
            meeting_id=meeting_id,
            organization_id=organization_id,
            updates={
                "status": MeetingRecordStatus.COMPLETED.value,
                "completed_at": completed_at or datetime.now(timezone.utc),
            },
        )

    async def mark_failed(
        self,
        *,
        meeting_id: str,
        error_message: str,
        organization_id: str | None = None,
    ) -> MeetingRecord | None:
        """Mark a meeting record as failed."""
        return await self._update_record(
            meeting_id=meeting_id,
            organization_id=organization_id,
            updates={
                "status": MeetingRecordStatus.FAILED.value,
                "error_message": error_message,
            },
        )

    async def _update_record(
        self,
        *,
        meeting_id: str,
        organization_id: str | None,
        updates: dict[str, object],
    ) -> MeetingRecord | None:
        query: dict[str, str] = {"_id": meeting_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        document = await self.collection.find_one_and_update(
            query,
            {
                "$set": {
                    **updates,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return MeetingRecord(**document)
