"""Meeting transcript persistence models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MeetingTranscriptItem(BaseModel):
    """Durable meeting transcript segment stored per meeting block."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    meeting_id: str
    organization_id: str
    block_id: str
    segment_id: str
    block_sequence: int = Field(ge=0)
    segment_index: int = Field(ge=0)
    speaker_key: int | None = None
    speaker_label: str
    text: str
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    created_at: datetime
    updated_at: datetime
