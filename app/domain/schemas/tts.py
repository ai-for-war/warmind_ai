"""Text-to-speech request/response schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SynthesizeRequest(BaseModel):
    """Schema for WebSocket synthesize request payload."""

    action: str = Field(default="synthesize")
    text: str = Field(..., min_length=1, max_length=10000)
    voice_id: str
    organization_id: Optional[str] = None
    speed: Optional[float] = None
    volume: Optional[float] = None
    pitch: Optional[int] = None
    emotion: Optional[str] = None


class GenerateAudioRequest(BaseModel):
    """Schema for synchronous audio generation request body."""

    text: str = Field(..., min_length=1, max_length=10000)
    voice_id: str
    speed: Optional[float] = None
    volume: Optional[float] = None
    pitch: Optional[int] = None
    emotion: Optional[str] = None


class StreamAudioRequest(BaseModel):
    """Schema for async TTS streaming trigger request body."""

    text: str = Field(..., min_length=1, max_length=10000)
    voice_id: str
    speed: Optional[float] = None
    volume: Optional[float] = None
    pitch: Optional[int] = None
    emotion: Optional[str] = None


class AudioFileRecord(BaseModel):
    """Schema representing generated audio metadata."""

    id: str
    organization_id: str
    created_by: str
    voice_id: str
    source_text: str
    audio_url: str
    audio_public_id: str
    duration_ms: int
    size_bytes: int
    format: str
    created_at: datetime


class AudioDetailResponse(BaseModel):
    """Schema for audio detail response including signed URL."""

    audio: AudioFileRecord
    signed_url: str


class AudioListResponse(BaseModel):
    """Schema for paginated generated audio list response."""

    items: list[AudioFileRecord]
    total: int
    skip: int
    limit: int


class GenerateAudioResponse(BaseModel):
    """Schema for sync generate-audio endpoint response."""

    audio: AudioFileRecord
    signed_url: str


class StreamAudioResponse(BaseModel):
    """Schema for async stream trigger response."""

    request_id: str
    status: str = "accepted"
