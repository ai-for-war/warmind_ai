"""Audio file model for generated speech metadata storage."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AudioFile(BaseModel):
    """Audio file domain model representing generated TTS audio metadata."""

    id: str = Field(alias="_id")
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
    deleted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
