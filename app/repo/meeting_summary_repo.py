"""Repository for durable meeting summary state."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.domain.models.meeting_summary import MeetingSummary, MeetingSummaryStatus


class MeetingSummaryRepository:
    """Database access wrapper for durable meeting summaries."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.meeting_summaries

    async def get_latest_by_meeting(
        self,
        *,
        meeting_id: str,
        organization_id: str | None = None,
    ) -> MeetingSummary | None:
        """Return the latest summary state for one meeting."""
        query: dict[str, str] = {"meeting_id": meeting_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        document = await self.collection.find_one(query)
        if document is None:
            return None
        return MeetingSummary(**document)

    async def upsert_latest_summary(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        language: str,
        status: MeetingSummaryStatus | str,
        bullets: Sequence[str],
        is_final: bool,
        source_block_sequence: int,
        error_message: str | None = None,
    ) -> MeetingSummary:
        """Create or replace the latest durable summary for a meeting."""
        existing = await self.get_latest_by_meeting(
            meeting_id=meeting_id,
            organization_id=organization_id,
        )
        if self._should_skip_update(
            existing=existing,
            source_block_sequence=source_block_sequence,
            is_final=is_final,
        ):
            return existing

        now = datetime.now(timezone.utc)
        document = await self.collection.find_one_and_update(
            {"meeting_id": meeting_id},
            {
                "$set": {
                    "organization_id": organization_id,
                    "language": language,
                    "status": self._status_value(status),
                    "bullets": list(bullets),
                    "is_final": is_final,
                    "source_block_sequence": source_block_sequence,
                    "error_message": error_message,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "_id": uuid4().hex,
                    "meeting_id": meeting_id,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return MeetingSummary(**document)

    async def mark_status(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        language: str,
        status: MeetingSummaryStatus | str,
        source_block_sequence: int,
        is_final: bool = False,
        error_message: str | None = None,
        bullets: Sequence[str] | None = None,
    ) -> MeetingSummary:
        """Update durable summary status without discarding prior bullets."""
        existing = await self.get_latest_by_meeting(
            meeting_id=meeting_id,
            organization_id=organization_id,
        )
        if self._should_skip_update(
            existing=existing,
            source_block_sequence=source_block_sequence,
            is_final=is_final,
        ):
            return existing

        now = datetime.now(timezone.utc)
        update_fields: dict[str, object] = {
            "organization_id": organization_id,
            "language": language,
            "status": self._status_value(status),
            "is_final": is_final,
            "source_block_sequence": source_block_sequence,
            "error_message": error_message,
            "updated_at": now,
        }
        if bullets is not None:
            update_fields["bullets"] = list(bullets)

        document = await self.collection.find_one_and_update(
            {"meeting_id": meeting_id},
            {
                "$set": update_fields,
                "$setOnInsert": {
                    "_id": uuid4().hex,
                    "meeting_id": meeting_id,
                    "created_at": now,
                    "bullets": [],
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return MeetingSummary(**document)

    @staticmethod
    def _status_value(status: MeetingSummaryStatus | str) -> str:
        if isinstance(status, MeetingSummaryStatus):
            return status.value
        return status

    @staticmethod
    def _should_skip_update(
        *,
        existing: MeetingSummary | None,
        source_block_sequence: int,
        is_final: bool,
    ) -> bool:
        if existing is None:
            return False
        if existing.is_final and not is_final:
            return True
        return existing.source_block_sequence > source_block_sequence
