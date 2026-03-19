"""Meeting record persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MeetingRecordStatus(str, Enum):
    """Durable lifecycle states for a meeting record."""

    ACTIVE = "active"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"


class MeetingRecord(BaseModel):
    """Durable meeting lifecycle record."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    user_id: str
    organization_id: str
    language: str
    status: MeetingRecordStatus = MeetingRecordStatus.ACTIVE
    provider: str
    started_at: datetime
    updated_at: datetime
    stopped_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
