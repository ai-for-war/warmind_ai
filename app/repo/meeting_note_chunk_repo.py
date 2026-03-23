"""Repository for meeting note chunk persistence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, ReturnDocument

from app.domain.models.meeting_note_chunk import (
    MeetingNoteActionItem,
    MeetingNoteChunk,
)


class MeetingNoteChunkRepository:
    """Database access wrapper for durable incremental meeting note chunks."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.meeting_note_chunks

    async def append(
        self,
        *,
        meeting_id: str,
        from_sequence: int,
        to_sequence: int,
        key_points: Sequence[str] | None = None,
        decisions: Sequence[str] | None = None,
        action_items: Sequence[MeetingNoteActionItem | dict[str, object]] | None = None,
        note_id: str | None = None,
        created_at: datetime | None = None,
    ) -> MeetingNoteChunk:
        """Persist one structured meeting note chunk idempotently by range."""
        normalized_action_items = self._normalize_action_items(action_items)
        validated = MeetingNoteChunk(
            _id=note_id or uuid4().hex,
            meeting_id=meeting_id,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            key_points=list(key_points or []),
            decisions=list(decisions or []),
            action_items=[
                item.model_dump(mode="python") for item in normalized_action_items
            ],
            created_at=created_at or datetime.now(timezone.utc),
        )
        document = validated.model_dump(by_alias=True, mode="python")
        persisted = await self.collection.find_one_and_update(
            {
                "meeting_id": meeting_id,
                "from_sequence": from_sequence,
                "to_sequence": to_sequence,
            },
            {"$setOnInsert": document},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return MeetingNoteChunk(**persisted)

    async def get_by_sequence_range(
        self,
        *,
        meeting_id: str,
        from_sequence: int,
        to_sequence: int,
    ) -> MeetingNoteChunk | None:
        """Get one note chunk by its meeting-local utterance range."""
        document = await self.collection.find_one(
            {
                "meeting_id": meeting_id,
                "from_sequence": from_sequence,
                "to_sequence": to_sequence,
            }
        )
        if document is None:
            return None
        return MeetingNoteChunk(**document)

    async def list_by_meeting(
        self,
        *,
        meeting_id: str,
        limit: int | None = None,
    ) -> list[MeetingNoteChunk]:
        """Return note chunks in ascending range order for one meeting."""
        cursor = self.collection.find({"meeting_id": meeting_id}).sort(
            [("from_sequence", ASCENDING), ("to_sequence", ASCENDING)]
        )
        if limit is not None:
            cursor = cursor.limit(limit)

        documents = [document async for document in cursor]
        return [MeetingNoteChunk(**document) for document in documents]

    async def list_by_meeting_paginated(
        self,
        *,
        meeting_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[MeetingNoteChunk]:
        """Return one paginated slice of note chunks for one meeting."""
        cursor = (
            self.collection.find({"meeting_id": meeting_id})
            .sort([("from_sequence", ASCENDING), ("to_sequence", ASCENDING)])
            .skip(skip)
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [MeetingNoteChunk(**document) for document in documents]

    async def count_by_meeting(
        self,
        *,
        meeting_id: str,
    ) -> int:
        """Count persisted note chunks for one meeting."""
        return await self.collection.count_documents({"meeting_id": meeting_id})

    @staticmethod
    def _normalize_action_items(
        action_items: Sequence[MeetingNoteActionItem | dict[str, object]] | None,
    ) -> list[MeetingNoteActionItem]:
        if action_items is None:
            return []
        return [
            item
            if isinstance(item, MeetingNoteActionItem)
            else MeetingNoteActionItem.model_validate(item)
            for item in action_items
        ]
