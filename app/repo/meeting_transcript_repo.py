"""Repository for durable meeting transcript persistence and pagination."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, ReturnDocument

from app.domain.models.meeting_transcript_item import MeetingTranscriptItem
from app.domain.schemas.meeting_transcript import MeetingTranscriptSegmentPayload


class MeetingTranscriptRepository:
    """Database access wrapper for stored meeting transcript segments."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.meeting_transcript_items

    async def upsert_block_segments(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        block_id: str,
        block_sequence: int,
        segments: Sequence[MeetingTranscriptSegmentPayload],
    ) -> list[MeetingTranscriptItem]:
        """Persist finalized transcript segments for one closed block."""
        now = datetime.now(timezone.utc)
        persisted: list[MeetingTranscriptItem] = []

        for segment_index, segment in enumerate(segments):
            result = await self.collection.find_one_and_update(
                {
                    "meeting_id": meeting_id,
                    "segment_id": segment.segment_id,
                },
                {
                    "$set": {
                        "organization_id": organization_id,
                        "block_id": block_id,
                        "block_sequence": block_sequence,
                        "segment_index": segment_index,
                        "speaker_key": segment.speaker_key,
                        "speaker_label": segment.speaker_label,
                        "text": segment.text,
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                        "updated_at": now,
                    },
                    "$setOnInsert": {
                        "_id": uuid4().hex,
                        "meeting_id": meeting_id,
                        "segment_id": segment.segment_id,
                        "created_at": now,
                    },
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            persisted.append(MeetingTranscriptItem(**result))

        persisted.sort(key=lambda item: (item.block_sequence, item.segment_index))
        return persisted

    async def list_by_meeting(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        after: tuple[int, int] | None = None,
        limit: int = 50,
    ) -> list[MeetingTranscriptItem]:
        """Return meeting transcript items in oldest-first block/segment order."""
        query: dict[str, object] = {
            "meeting_id": meeting_id,
            "organization_id": organization_id,
        }
        if after is not None:
            block_sequence, segment_index = after
            query["$or"] = [
                {"block_sequence": {"$gt": block_sequence}},
                {
                    "block_sequence": block_sequence,
                    "segment_index": {"$gt": segment_index},
                },
            ]

        cursor = (
            self.collection.find(query)
            .sort(
                [
                    ("block_sequence", ASCENDING),
                    ("segment_index", ASCENDING),
                ]
            )
            .limit(limit)
        )

        documents: list[MeetingTranscriptItem] = []
        async for document in cursor:
            documents.append(MeetingTranscriptItem(**document))
        return documents

    async def count_by_meeting(
        self,
        *,
        meeting_id: str,
        organization_id: str,
    ) -> int:
        """Count stored transcript items for one meeting."""
        return await self.collection.count_documents(
            {
                "meeting_id": meeting_id,
                "organization_id": organization_id,
            }
        )
