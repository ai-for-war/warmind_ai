"""Schemas for meeting summary payloads."""

from __future__ import annotations

from pydantic import Field

from app.domain.models.meeting_summary import MeetingSummaryStatus
from app.domain.schemas.meeting_record import MeetingRecordBaseSchema


class MeetingSummaryPayload(MeetingRecordBaseSchema):
    """Normalized payload for meeting summary state delivery."""

    meeting_id: str = Field(..., min_length=1, max_length=128)
    status: MeetingSummaryStatus
    bullets: list[str] = Field(default_factory=list)
    is_final: bool
    language: str = Field(..., min_length=2, max_length=32)
    source_block_sequence: int = Field(..., ge=0)
    error_message: str | None = Field(default=None, min_length=1, max_length=500)
