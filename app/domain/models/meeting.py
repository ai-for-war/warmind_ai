"""Meeting transcript session persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MeetingStatus(str, Enum):
    """Durable lifecycle states for a live meeting transcript session."""

    STREAMING = "streaming"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class MeetingArchiveScope(str, Enum):
    """Archive-scope filters for meeting management APIs."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    ALL = "all"


class Meeting(BaseModel):
    """Durable meeting transcript session record."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=True,
    )

    id: str = Field(alias="_id")
    organization_id: str
    created_by: str
    title: str | None = None
    source: str = "google_meet"
    status: MeetingStatus = MeetingStatus.STREAMING
    language: str | None = None
    stream_id: str
    started_at: datetime
    ended_at: datetime | None = None
    error_message: str | None = None
    archived_at: datetime | None = None
    archived_by: str | None = None

    @property
    def is_archived(self) -> bool:
        """Return whether archive metadata currently marks this meeting hidden."""
        return self.archived_at is not None

    @field_validator("title", "error_message", "archived_by", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Collapse blank optional strings to null for stable persistence."""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        """Persist language values in a normalized lowercase form."""
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: str | None) -> str:
        """Persist the meeting source as a normalized string value."""
        if value is None:
            return "google_meet"
        normalized = value.strip().lower()
        return normalized or "google_meet"
