"""Repository for durable meeting summary jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING, ReturnDocument

from app.domain.models.meeting_summary_job import (
    MeetingSummaryJob,
    MeetingSummaryJobKind,
    MeetingSummaryJobStatus,
)


class MeetingSummaryJobRepository:
    """Database access wrapper for meeting summary job lifecycle."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.meeting_summary_jobs

    async def create_or_get_pending_job(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        user_id: str,
        job_kind: MeetingSummaryJobKind | str,
        target_block_sequence: int,
    ) -> MeetingSummaryJob:
        """Create one durable job or return the existing deduplicated job."""
        now = datetime.now(timezone.utc)
        normalized_job_kind = self._job_kind_value(job_kind)
        query = {
            "meeting_id": meeting_id,
            "job_kind": normalized_job_kind,
            "target_block_sequence": target_block_sequence,
        }

        await self.collection.update_one(
            query,
            {
                "$setOnInsert": {
                    "_id": uuid4().hex,
                    "meeting_id": meeting_id,
                    "organization_id": organization_id,
                    "user_id": user_id,
                    "job_kind": normalized_job_kind,
                    "target_block_sequence": target_block_sequence,
                    "status": MeetingSummaryJobStatus.PENDING.value,
                    "retry_count": 0,
                    "queued_at": now,
                    "started_at": None,
                    "completed_at": None,
                    "error_message": None,
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

        document = await self.collection.find_one(query)
        if document is None:
            raise RuntimeError("Failed to load meeting summary job after upsert")
        return MeetingSummaryJob(**document)

    async def claim_pending_job(self, job_id: str) -> MeetingSummaryJob | None:
        """Atomically transition one summary job from pending to processing."""
        now = datetime.now(timezone.utc)
        document = await self.collection.find_one_and_update(
            {
                "_id": job_id,
                "status": MeetingSummaryJobStatus.PENDING.value,
            },
            {
                "$set": {
                    "status": MeetingSummaryJobStatus.PROCESSING.value,
                    "started_at": now,
                    "error_message": None,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return MeetingSummaryJob(**document)

    async def mark_completed(self, job_id: str) -> MeetingSummaryJob | None:
        """Mark one claimed summary job as completed."""
        now = datetime.now(timezone.utc)
        document = await self.collection.find_one_and_update(
            {
                "_id": job_id,
                "status": MeetingSummaryJobStatus.PROCESSING.value,
            },
            {
                "$set": {
                    "status": MeetingSummaryJobStatus.COMPLETED.value,
                    "completed_at": now,
                    "error_message": None,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return MeetingSummaryJob(**document)

    async def mark_failed(
        self,
        *,
        job_id: str,
        error_message: str,
    ) -> MeetingSummaryJob | None:
        """Mark one summary job as failed with a terminal error."""
        now = datetime.now(timezone.utc)
        document = await self.collection.find_one_and_update(
            {
                "_id": job_id,
                "status": {
                    "$in": [
                        MeetingSummaryJobStatus.PENDING.value,
                        MeetingSummaryJobStatus.PROCESSING.value,
                    ]
                },
            },
            {
                "$set": {
                    "status": MeetingSummaryJobStatus.FAILED.value,
                    "completed_at": now,
                    "error_message": error_message,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return MeetingSummaryJob(**document)

    async def get_latest_job(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        job_kind: MeetingSummaryJobKind | str | None = None,
    ) -> MeetingSummaryJob | None:
        """Return the newest job for one meeting, optionally filtered by kind."""
        query: dict[str, object] = {
            "meeting_id": meeting_id,
            "organization_id": organization_id,
        }
        if job_kind is not None:
            query["job_kind"] = self._job_kind_value(job_kind)

        document = await self.collection.find_one(
            query,
            sort=[
                ("target_block_sequence", DESCENDING),
                ("queued_at", DESCENDING),
            ],
        )
        if document is None:
            return None
        return MeetingSummaryJob(**document)

    @staticmethod
    def _job_kind_value(job_kind: MeetingSummaryJobKind | str) -> str:
        if isinstance(job_kind, MeetingSummaryJobKind):
            return job_kind.value
        return job_kind
