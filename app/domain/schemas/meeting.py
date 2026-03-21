"""Schemas for durable meeting transcript records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models.meeting import MeetingStatus


class MeetingSchemaBase(BaseModel):
    """Base schema for meeting-related durable payloads."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        use_enum_values=True,
    )


class MeetingRecord(MeetingSchemaBase):
    """Schema representing one durable meeting session."""

    id: str = Field(..., min_length=1)
    organization_id: str = Field(..., min_length=1)
    created_by: str = Field(..., min_length=1)
    title: str | None = None
    source: str = Field(default="google_meet", min_length=1)
    status: MeetingStatus = MeetingStatus.STREAMING
    language: str | None = None
    stream_id: str = Field(..., min_length=1, max_length=128)
    started_at: datetime
    ended_at: datetime | None = None
    error_message: str | None = None


class MeetingUtteranceMessageRecord(MeetingSchemaBase):
    """Schema representing one speaker-grouped transcript message."""

    speaker_index: int = Field(..., ge=0)
    speaker_label: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_label(self) -> "MeetingUtteranceMessageRecord":
        """Require the label to remain aligned with the speaker index."""
        expected = f"speaker_{self.speaker_index + 1}"
        if self.speaker_label != expected:
            raise ValueError(
                f"speaker_label must match speaker_index as '{expected}'"
            )
        return self


class MeetingUtteranceRecord(MeetingSchemaBase):
    """Schema representing one durable canonical meeting utterance."""

    id: str = Field(..., min_length=1)
    meeting_id: str = Field(..., min_length=1)
    sequence: int = Field(..., ge=1)
    messages: list[MeetingUtteranceMessageRecord] = Field(..., min_length=1)
    created_at: datetime
