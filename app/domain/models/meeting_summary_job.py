"""Meeting summary job persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MeetingSummaryJobKind(str, Enum):
    """Supported meeting summary job kinds."""

    LIVE = "live"
    FINALIZE = "finalize"


class MeetingSummaryJobStatus(str, Enum):
    """Durable lifecycle states for summary jobs."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MeetingSummaryJob(BaseModel):
    """Persisted async job used for live/final meeting summaries."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    meeting_id: str
    organization_id: str
    user_id: str
    job_kind: MeetingSummaryJobKind = MeetingSummaryJobKind.LIVE
    target_block_sequence: int = Field(ge=0)
    status: MeetingSummaryJobStatus = MeetingSummaryJobStatus.PENDING
    retry_count: int = Field(default=0, ge=0)
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
