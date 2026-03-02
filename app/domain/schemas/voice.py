"""Voice cloning and voice management request/response schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.models.voice import VoiceType


class CloneVoiceRequest(BaseModel):
    """Schema for clone voice multipart form fields (non-file fields)."""

    name: str = Field(..., min_length=1, max_length=255)
    voice_id: str = Field(
        ...,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{7,255}$",
    )


class PreviewVoiceRequest(BaseModel):
    """Schema for preview voice request body."""

    text: str = Field(..., min_length=1, max_length=200)


class VoiceRecord(BaseModel):
    """Schema representing a cloned voice record."""

    id: str
    voice_id: str
    name: str
    voice_type: VoiceType
    organization_id: str
    created_by: str
    source_audio_url: str
    source_audio_public_id: str
    language: Optional[str] = None
    created_at: datetime

    class Config:
        use_enum_values = True


class SystemVoiceRecord(BaseModel):
    """Schema representing a system voice from MiniMax catalog."""

    voice_id: str
    voice_name: str
    description: Optional[str] = None
    created_time: Optional[datetime] = None


class VoiceDetailResponse(BaseModel):
    """Schema for voice detail response including signed source audio URL."""

    voice: VoiceRecord
    source_audio_signed_url: Optional[str] = None


class VoiceListResponse(BaseModel):
    """Schema for voice list response (system voices + cloned voices)."""

    system_voices: list[SystemVoiceRecord]
    cloned_voices: list[VoiceRecord]
    total_cloned: int


class CloneVoiceResponse(BaseModel):
    """Schema for clone voice endpoint response."""

    voice: VoiceRecord
    preview_url: Optional[str] = None
