"""Schemas for live speech-to-text Socket.IO payloads.

The public contract in this module is intentionally provider-agnostic. Socket
handlers and frontend clients work with normalized STT lifecycle payloads
without depending on Deepgram event names or SDK response objects.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PHASE1_STT_ENCODING = "linear16"
PHASE1_STT_SAMPLE_RATE = 16000
PHASE1_STT_CHANNELS = 2
STTSpeakerRole = Literal["interviewer", "user"]
STTChannelIndex = Literal[0, 1]


class STTBaseSchema(BaseModel):
    """Base schema with strict payload validation for STT socket contracts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class STTChannelMap(STTBaseSchema):
    """Explicit mapping between interview audio channels and speaker roles."""

    channel_0: STTSpeakerRole = Field(alias="0")
    channel_1: STTSpeakerRole = Field(alias="1")

    @model_validator(mode="after")
    def validate_roles(self) -> "STTChannelMap":
        """Require exactly one interviewer channel and one user channel."""
        roles = {self.channel_0, self.channel_1}
        if roles != {"interviewer", "user"}:
            raise ValueError(
                "channel_map must assign exactly one 'interviewer' and one 'user'"
            )
        return self

    def role_for_channel(self, channel: int) -> STTSpeakerRole:
        """Resolve the declared speaker role for a supported channel index."""
        if channel == 0:
            return self.channel_0
        if channel == 1:
            return self.channel_1
        raise ValueError("Unsupported interview channel index")


class STTStartRequest(STTBaseSchema):
    """Payload for `stt:start` requests.

    Phase 1 supports exactly one active stream per socket connection. Frontend
    callers must finalize or stop the current stream before starting another
    stream on the same Socket.IO connection.
    """

    stream_id: str = Field(..., min_length=1, max_length=128)
    conversation_id: str = Field(..., min_length=1, max_length=128)
    language: str | None = Field(default=None, min_length=2, max_length=32)
    encoding: Literal["linear16"] = PHASE1_STT_ENCODING
    sample_rate: Literal[16000] = PHASE1_STT_SAMPLE_RATE
    channels: Literal[2] = PHASE1_STT_CHANNELS
    channel_map: STTChannelMap

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        """Normalize language values while preserving provider validation later."""
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None


class STTAudioMetadata(STTBaseSchema):
    """Metadata accompanying a binary `stt:audio` payload.

    `sequence` is required and should increase monotonically per stream.
    Interview multichannel frames preserve the existing sequence/timestamp
    metadata while repeating the stream contract required by the backend.
    """

    stream_id: str = Field(..., min_length=1, max_length=128)
    conversation_id: str = Field(..., min_length=1, max_length=128)
    encoding: Literal["linear16"] = PHASE1_STT_ENCODING
    sample_rate: Literal[16000] = PHASE1_STT_SAMPLE_RATE
    channels: Literal[2] = PHASE1_STT_CHANNELS
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


class STTFinalizeRequest(STTBaseSchema):
    """Payload for `stt:finalize` requests."""

    stream_id: str = Field(..., min_length=1, max_length=128)


class STTStopRequest(STTBaseSchema):
    """Payload for `stt:stop` requests."""

    stream_id: str = Field(..., min_length=1, max_length=128)


class STTStartedPayload(STTBaseSchema):
    """Normalized payload for `stt:started` events."""

    stream_id: str
    conversation_id: str
    language: str = "en"
    encoding: Literal["linear16"] = PHASE1_STT_ENCODING
    sample_rate: Literal[16000] = PHASE1_STT_SAMPLE_RATE
    channels: Literal[2] = PHASE1_STT_CHANNELS
    channel_map: STTChannelMap


class STTPartialPayload(STTBaseSchema):
    """Normalized payload for non-final transcript updates."""

    stream_id: str
    conversation_id: str
    source: STTSpeakerRole | None = None
    channel: STTChannelIndex | None = None
    transcript: str = ""
    is_final: Literal[False] = False


class STTFinalPayload(STTBaseSchema):
    """Normalized payload for a committed transcript segment.

    Phase 1 exposes provider-agnostic timing and confidence fields so the UI can
    optionally render richer transcript metadata without binding to provider
    response types. They remain optional because not every provider event will
    carry them.
    """

    stream_id: str
    conversation_id: str
    source: STTSpeakerRole | None = None
    channel: STTChannelIndex | None = None
    transcript: str = Field(..., min_length=1)
    is_final: Literal[True] = True
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)


class STTCompletedPayload(STTBaseSchema):
    """Normalized payload for `stt:completed` events."""

    stream_id: str
    conversation_id: str
    status: Literal["completed"] = "completed"


class STTErrorPayload(STTBaseSchema):
    """Normalized payload for `stt:error` events."""

    stream_id: str | None = None
    error_code: str = Field(..., min_length=1, max_length=64)
    error_message: str = Field(..., min_length=1, max_length=500)
    retryable: bool = False


class STTUtteranceClosedPayload(STTBaseSchema):
    """Normalized payload for committed stable interview utterances."""

    conversation_id: str = Field(..., min_length=1, max_length=128)
    utterance_id: str = Field(..., min_length=1, max_length=128)
    source: STTSpeakerRole
    channel: STTChannelIndex
    text: str = Field(..., min_length=1)
    started_at: datetime
    ended_at: datetime
    turn_closed_at: datetime


class InterviewAnswerPayload(STTBaseSchema):
    """Text-only AI answer payload emitted for an interview conversation."""

    conversation_id: str = Field(..., min_length=1, max_length=128)
    text: str = Field(..., min_length=1)
