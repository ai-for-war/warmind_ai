"""Interview utterance persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

InterviewSpeakerRole = Literal["interviewer", "user"]
InterviewChannelIndex = Literal[0, 1]


class InterviewUtteranceStatus(str, Enum):
    """Durable statuses allowed in persistent interview utterance storage."""

    CLOSED = "closed"


DURABLE_INTERVIEW_UTTERANCE_STATUSES = frozenset(
    {InterviewUtteranceStatus.CLOSED.value}
)


class InterviewUtterance(BaseModel):
    """Durable interview utterance record."""

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str = Field(alias="_id")
    conversation_id: str
    source: InterviewSpeakerRole
    channel: InterviewChannelIndex
    text: str
    status: InterviewUtteranceStatus = InterviewUtteranceStatus.CLOSED
    started_at: datetime
    ended_at: datetime
    turn_closed_at: datetime
    created_at: datetime
