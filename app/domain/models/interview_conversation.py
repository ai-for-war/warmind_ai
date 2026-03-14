"""Interview conversation persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

InterviewSpeakerRole = Literal["interviewer", "user"]


class InterviewConversationStatus(str, Enum):
    """Durable lifecycle states for an interview conversation."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class InterviewChannelMap(BaseModel):
    """Stable storage representation of a 2-channel interview mapping."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    channel_0: InterviewSpeakerRole = Field(alias="0")
    channel_1: InterviewSpeakerRole = Field(alias="1")

    @model_validator(mode="after")
    def validate_roles(self) -> "InterviewChannelMap":
        """Require exactly one interviewer channel and one user channel."""
        roles = {self.channel_0, self.channel_1}
        if roles != {"interviewer", "user"}:
            raise ValueError(
                "channel_map must assign exactly one 'interviewer' and one 'user'"
            )
        return self


class InterviewConversation(BaseModel):
    """Durable interview conversation record."""

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str = Field(alias="_id")
    conversation_id: str
    user_id: str
    organization_id: str | None = None
    channel_map: InterviewChannelMap
    status: InterviewConversationStatus = InterviewConversationStatus.ACTIVE
    started_at: datetime
    ended_at: datetime | None = None
