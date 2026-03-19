"""Schemas for meeting recording Socket.IO payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MEETING_RECORD_ENCODING = "linear16"
MEETING_RECORD_SAMPLE_RATE = 16000
MEETING_RECORD_CHANNELS = 1


class MeetingRecordBaseSchema(BaseModel):
    """Base schema with strict validation for meeting socket contracts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MeetingRecordStartRequest(MeetingRecordBaseSchema):
    """Payload for `meeting_record:start` requests."""

    organization_id: str = Field(..., min_length=1, max_length=128)
    language: str = Field(
        default="en",
        min_length=2,
        max_length=32,
        validate_default=True,
    )
    encoding: Literal["linear16"] = MEETING_RECORD_ENCODING
    sample_rate: Literal[16000] = MEETING_RECORD_SAMPLE_RATE
    channels: Literal[1] = MEETING_RECORD_CHANNELS

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        """Normalize incoming language codes to lowercase."""
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("language must not be empty")
        return normalized


class MeetingRecordAudioMetadata(MeetingRecordBaseSchema):
    """Metadata accompanying a binary `meeting_record:audio` payload."""

    meeting_id: str = Field(..., min_length=1, max_length=128)
    sequence: int = Field(..., ge=0)
    timestamp_ms: int | None = Field(default=None, ge=0)
    encoding: Literal["linear16"] = MEETING_RECORD_ENCODING
    sample_rate: Literal[16000] = MEETING_RECORD_SAMPLE_RATE
    channels: Literal[1] = MEETING_RECORD_CHANNELS


class MeetingRecordStopRequest(MeetingRecordBaseSchema):
    """Payload for `meeting_record:stop` requests."""

    meeting_id: str = Field(..., min_length=1, max_length=128)


class MeetingRecordStartedPayload(MeetingRecordBaseSchema):
    """Normalized payload for `meeting_record:started` events."""

    meeting_id: str
    organization_id: str
    language: str
    status: Literal["active"] = "active"
    encoding: Literal["linear16"] = MEETING_RECORD_ENCODING
    sample_rate: Literal[16000] = MEETING_RECORD_SAMPLE_RATE
    channels: Literal[1] = MEETING_RECORD_CHANNELS


class MeetingRecordStoppingPayload(MeetingRecordBaseSchema):
    """Normalized payload for `meeting_record:stopping` events."""

    meeting_id: str
    status: Literal["stopping"] = "stopping"


class MeetingRecordCompletedPayload(MeetingRecordBaseSchema):
    """Normalized payload for `meeting_record:completed` events."""

    meeting_id: str
    status: Literal["completed"] = "completed"


class MeetingRecordErrorPayload(MeetingRecordBaseSchema):
    """Normalized payload for `meeting_record:error` events."""

    meeting_id: str | None = None
    error_code: str = Field(..., min_length=1, max_length=64)
    error_message: str = Field(..., min_length=1, max_length=500)
    retryable: bool = False
