"""Voice model and related enums for cloned/system voice metadata."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class VoiceType(str, Enum):
    """Type of voice record."""

    SYSTEM = "system"
    CLONED = "cloned"


class Voice(BaseModel):
    """Voice domain model representing metadata stored in MongoDB."""

    id: str = Field(alias="_id")
    voice_id: str
    name: str
    voice_type: VoiceType
    organization_id: str
    created_by: str
    source_audio_url: str
    source_audio_public_id: str
    language: Optional[str] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        use_enum_values = True
