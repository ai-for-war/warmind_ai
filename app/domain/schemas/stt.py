"""Schemas for live speech-to-text Socket.IO payloads.

The public contract in this module is intentionally provider-agnostic. Socket
handlers and frontend clients work with normalized STT lifecycle payloads
without depending on Deepgram event names or SDK response objects.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PHASE1_STT_ENCODING = "linear16"
PHASE1_STT_SAMPLE_RATE = 16000
PHASE1_STT_CHANNELS = 1


class STTBaseSchema(BaseModel):
    """Base schema with strict payload validation for STT socket contracts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class STTStartRequest(STTBaseSchema):
    """Payload for `stt:start` requests."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    language: str | None = Field(default=None, min_length=2, max_length=32)
    encoding: Literal["linear16"] = PHASE1_STT_ENCODING
    sample_rate: Literal[16000] = PHASE1_STT_SAMPLE_RATE
    channels: Literal[1] = PHASE1_STT_CHANNELS

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        """Normalize language values while preserving provider validation later."""
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None


class STTAudioMetadata(STTBaseSchema):
    """Metadata accompanying a binary `stt:audio` payload."""

    stream_id: str = Field(..., min_length=1, max_length=128)
    sequence: int = Field(..., ge=0)
    timestamp_ms: int | None = Field(default=None, ge=0)


class STTFinalizeRequest(STTBaseSchema):
    """Payload for `stt:finalize` requests."""

    stream_id: str = Field(..., min_length=1, max_length=128)


class STTStopRequest(STTBaseSchema):
    """Payload for `stt:stop` requests."""

    stream_id: str = Field(..., min_length=1, max_length=128)


class STTStartedPayload(STTBaseSchema):
    """Normalized payload for `stt:started` events."""

    stream_id: str
    language: str = "en"
    encoding: Literal["linear16"] = PHASE1_STT_ENCODING
    sample_rate: Literal[16000] = PHASE1_STT_SAMPLE_RATE
    channels: Literal[1] = PHASE1_STT_CHANNELS


class STTPartialPayload(STTBaseSchema):
    """Normalized payload for non-final transcript updates."""

    stream_id: str
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
    transcript: str = Field(..., min_length=1)
    is_final: Literal[True] = True
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)


class STTCompletedPayload(STTBaseSchema):
    """Normalized payload for `stt:completed` events."""

    stream_id: str
    status: Literal["completed"] = "completed"


class STTErrorPayload(STTBaseSchema):
    """Normalized payload for `stt:error` events."""

    stream_id: str | None = None
    error_code: str = Field(..., min_length=1, max_length=64)
    error_message: str = Field(..., min_length=1, max_length=500)
    retryable: bool = False
