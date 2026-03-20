"""Meeting summary persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MeetingSummaryStatus(str, Enum):
    """Durable lifecycle states for a meeting summary."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MeetingSummary(BaseModel):
    """Latest durable summary state stored per meeting."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    meeting_id: str
    organization_id: str
    language: str
    status: MeetingSummaryStatus = MeetingSummaryStatus.PENDING
    bullets: list[str] = Field(default_factory=list)
    is_final: bool = False
    source_block_sequence: int = Field(ge=0)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
