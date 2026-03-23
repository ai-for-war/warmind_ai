"""Repository for meeting utterance persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from pymongo import ASCENDING, ReturnDocument

from app.domain.models.meeting_utterance import (
    MeetingUtterance,
    MeetingUtteranceMessage,
)


class MeetingUtteranceRepository:
    """Database access wrapper for canonical meeting utterances."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.meeting_utterances

    async def append(
        self,
        *,
        meeting_id: str,
        sequence: int,
        messages: Sequence[MeetingUtteranceMessage | BaseModel | Mapping[str, object]],
        utterance_id: str | None = None,
        created_at: datetime | None = None,
    ) -> MeetingUtterance:
        """Persist one canonical meeting utterance idempotently by sequence."""
        normalized_messages = self._normalize_messages(messages)
        document = {
            "_id": utterance_id or uuid4().hex,
            "meeting_id": meeting_id,
            "sequence": sequence,
            "messages": [
                message.model_dump(mode="python") for message in normalized_messages
            ],
            "created_at": created_at or datetime.now(timezone.utc),
        }
        persisted = await self.collection.find_one_and_update(
            {"meeting_id": meeting_id, "sequence": sequence},
            {"$setOnInsert": document},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return MeetingUtterance(**persisted)

    async def get_by_meeting_and_sequence(
        self,
        *,
        meeting_id: str,
        sequence: int,
    ) -> MeetingUtterance | None:
        """Get one canonical utterance by its meeting-local sequence number."""
        document = await self.collection.find_one(
            {
                "meeting_id": meeting_id,
                "sequence": sequence,
            }
        )
        if document is None:
            return None
        return MeetingUtterance(**document)

    async def list_by_meeting(
        self,
        *,
        meeting_id: str,
        limit: int | None = None,
    ) -> list[MeetingUtterance]:
        """Return meeting utterances in ascending sequence order."""
        cursor = self.collection.find({"meeting_id": meeting_id}).sort(
            [("sequence", ASCENDING)]
        )
        if limit is not None:
            cursor = cursor.limit(limit)

        documents = [document async for document in cursor]
        return [MeetingUtterance(**document) for document in documents]

    @staticmethod
    def _normalize_messages(
        messages: Sequence[MeetingUtteranceMessage | BaseModel | Mapping[str, object]],
    ) -> list[MeetingUtteranceMessage]:
        return [
            message
            if isinstance(message, MeetingUtteranceMessage)
            else MeetingUtteranceMessage.model_validate(
                message.model_dump(mode="python")
                if isinstance(message, BaseModel)
                else message
            )
            for message in messages
        ]
