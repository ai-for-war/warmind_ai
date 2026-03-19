"""Schemas for meeting transcript socket payloads."""

from __future__ import annotations

from pydantic import Field

from app.domain.schemas.meeting_record import MeetingRecordBaseSchema


class MeetingTranscriptSegmentPayload(MeetingRecordBaseSchema):
    """One speaker-tagged transcript segment inside a live meeting block."""

    segment_id: str = Field(..., min_length=1, max_length=128)
    speaker_key: int | None = None
    speaker_label: str = Field(..., min_length=1, max_length=64)
    text: str = Field(..., min_length=1, max_length=20000)
    is_final: bool
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)


class MeetingTranscriptBlockPayload(MeetingRecordBaseSchema):
    """Full current transcript block emitted to the frontend on each update."""

    meeting_id: str = Field(..., min_length=1, max_length=128)
    block_id: str = Field(..., min_length=1, max_length=128)
    sequence: int = Field(..., ge=0)
    segments: list[MeetingTranscriptSegmentPayload] = Field(default_factory=list)
    draft_segments: list[MeetingTranscriptSegmentPayload] = Field(default_factory=list)
    is_final: bool
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
