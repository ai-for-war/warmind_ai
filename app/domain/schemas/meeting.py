"""Schemas for meeting transcript records and realtime payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.models.meeting import MeetingStatus

PHASE1_MEETING_ENCODING = "linear16"
PHASE1_MEETING_SAMPLE_RATE = 16000
PHASE1_MEETING_CHANNELS = 1


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


class MeetingStartRequest(MeetingSchemaBase):
    """Payload for `meeting:start` requests."""

    organization_id: str = Field(..., min_length=1, max_length=128)
    stream_id: str = Field(..., min_length=1, max_length=128)
    title: str | None = None
    language: str | None = Field(default=None, min_length=2, max_length=32)
    source: Literal["google_meet"] = "google_meet"
    encoding: Literal["linear16"] = PHASE1_MEETING_ENCODING
    sample_rate: Literal[16000] = PHASE1_MEETING_SAMPLE_RATE
    channels: Literal[1] = PHASE1_MEETING_CHANNELS

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        """Normalize language values before provider-level validation."""
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None


class MeetingAudioMetadata(MeetingSchemaBase):
    """Metadata accompanying a binary `meeting:audio` payload."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    encoding: Literal["linear16"] = PHASE1_MEETING_ENCODING
    sample_rate: Literal[16000] = PHASE1_MEETING_SAMPLE_RATE
    channels: Literal[1] = PHASE1_MEETING_CHANNELS
    sequence: int = Field(
        ...,
        ge=0,
        description="Client-maintained monotonic frame sequence per stream.",
    )
    timestamp_ms: int | None = Field(
        default=None,
        ge=0,
        description="Optional client capture timestamp in milliseconds.",
    )


class MeetingFinalizeRequest(MeetingSchemaBase):
    """Payload for `meeting:finalize` requests."""

    stream_id: str = Field(..., min_length=1, max_length=128)


class MeetingStopRequest(MeetingSchemaBase):
    """Payload for `meeting:stop` requests."""

    stream_id: str = Field(..., min_length=1, max_length=128)


class MeetingStartedPayload(MeetingSchemaBase):
    """Payload emitted when a live meeting transcript session starts."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    language: str = Field(default="en", min_length=2, max_length=32)
    encoding: Literal["linear16"] = PHASE1_MEETING_ENCODING
    sample_rate: Literal[16000] = PHASE1_MEETING_SAMPLE_RATE
    channels: Literal[1] = PHASE1_MEETING_CHANNELS
    status: Literal["streaming"] = "streaming"


class MeetingFinalPayload(MeetingSchemaBase):
    """Payload emitted for one finalized realtime transcript fragment."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    utterance_id: str = Field(..., min_length=1, max_length=128)
    messages: list[MeetingUtteranceMessageRecord] = Field(..., min_length=1)
    is_final: Literal[True] = True


class MeetingUtteranceClosedPayload(MeetingSchemaBase):
    """Payload emitted when one canonical meeting utterance is persisted."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    utterance_id: str = Field(..., min_length=1, max_length=128)
    sequence: int = Field(..., ge=1)
    messages: list[MeetingUtteranceMessageRecord] = Field(..., min_length=1)
    created_at: datetime


class MeetingCompletedPayload(MeetingSchemaBase):
    """Payload emitted when a meeting session completes cleanly."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    status: Literal["completed"] = "completed"


class MeetingInterruptedPayload(MeetingSchemaBase):
    """Payload emitted when a meeting session ends in interrupted state."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=128)
    status: Literal["interrupted"] = "interrupted"


class MeetingErrorPayload(MeetingSchemaBase):
    """Payload emitted when a meeting session cannot continue."""

    stream_id: str | None = Field(default=None, min_length=1, max_length=128)
    meeting_id: str | None = Field(default=None, min_length=1, max_length=128)
    error_code: str = Field(..., min_length=1, max_length=64)
    error_message: str = Field(..., min_length=1, max_length=500)
    retryable: bool = False
