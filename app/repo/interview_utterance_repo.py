"""Repository for interview utterance persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.common.exceptions import InvalidInterviewConversationStateError
from app.domain.models.interview_utterance import (
    DURABLE_INTERVIEW_UTTERANCE_STATUSES,
    InterviewSpeakerRole,
    InterviewUtterance,
    InterviewUtteranceStatus,
)


class InterviewUtteranceRepository:
    """Database access wrapper for stable interview utterances."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.interview_utterances

    async def append_stable(
        self,
        *,
        conversation_id: str,
        source: InterviewSpeakerRole,
        channel: int,
        text: str,
        started_at: datetime,
        ended_at: datetime,
        turn_closed_at: datetime,
        utterance_id: str | None = None,
        status: InterviewUtteranceStatus = InterviewUtteranceStatus.CLOSED,
    ) -> InterviewUtterance:
        """Persist one durable, closed interview utterance."""
        status_value = self._normalize_status(status)
        if status_value not in DURABLE_INTERVIEW_UTTERANCE_STATUSES:
            raise InvalidInterviewConversationStateError(
                "Only closed stable interview utterances may be stored durably"
            )

        document = {
            "_id": utterance_id or uuid4().hex,
            "conversation_id": conversation_id,
            "source": source,
            "channel": channel,
            "text": text,
            "status": status_value,
            "started_at": started_at,
            "ended_at": ended_at,
            "turn_closed_at": turn_closed_at,
            "created_at": datetime.now(timezone.utc),
        }
        await self.collection.insert_one(document)
        return InterviewUtterance(**document)

    async def get_recent_durable_by_conversation(
        self,
        *,
        conversation_id: str,
        limit: int = 20,
    ) -> list[InterviewUtterance]:
        """Return a bounded recent durable utterance window in timeline order."""
        cursor = (
            self.collection.find(
                {
                    "conversation_id": conversation_id,
                    "status": {"$in": list(DURABLE_INTERVIEW_UTTERANCE_STATUSES)},
                }
            )
            .sort([("turn_closed_at", -1), ("created_at", -1)])
            .limit(limit)
        )

        documents: list[dict] = []
        async for document in cursor:
            documents.append(document)

        documents.reverse()
        return [InterviewUtterance(**document) for document in documents]

    @staticmethod
    def _normalize_status(status: InterviewUtteranceStatus | str) -> str:
        if isinstance(status, InterviewUtteranceStatus):
            return status.value
        return status
