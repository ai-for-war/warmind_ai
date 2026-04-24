"""Durable stock research schedule persistence models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models.stock_research_report import StockResearchReportRuntimeConfig


class StockResearchScheduleType(str, Enum):
    """Supported recurring stock research schedule types."""

    EVERY_15_MINUTES = "every_15_minutes"
    DAILY = "daily"
    WEEKLY = "weekly"


class StockResearchScheduleStatus(str, Enum):
    """Lifecycle states for one persisted stock research schedule."""

    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class StockResearchScheduleWeekday(str, Enum):
    """Weekdays supported by weekly stock research schedules."""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class StockResearchScheduleRunStatus(str, Enum):
    """Dispatch lifecycle for one schedule occurrence."""

    DISPATCHING = "dispatching"
    QUEUED = "queued"
    ENQUEUE_FAILED = "enqueue_failed"


class StockResearchScheduleModelBase(BaseModel):
    """Common persistence model settings for stock research schedule documents."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class StockResearchSchedule(StockResearchScheduleModelBase):
    """One user-owned recurring stock research schedule stored in MongoDB."""

    id: str | None = Field(default=None, alias="_id")
    user_id: str
    organization_id: str
    symbol: str
    runtime_config: StockResearchReportRuntimeConfig
    schedule_type: StockResearchScheduleType
    hour: int | None = None
    weekdays: list[StockResearchScheduleWeekday] = Field(default_factory=list)
    status: StockResearchScheduleStatus = StockResearchScheduleStatus.ACTIVE
    next_run_at: datetime
    created_at: datetime
    updated_at: datetime

    @field_validator("user_id", "organization_id", mode="before")
    @classmethod
    def normalize_scope_identifier(cls, value: str) -> str:
        """Require non-blank ownership identifiers."""
        if not isinstance(value, str):
            raise TypeError("ownership identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("ownership identifiers must not be blank")
        return normalized

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist scheduled stock symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("hour")
    @classmethod
    def validate_optional_hour(cls, value: int | None) -> int | None:
        """Require configured calendar hours to be whole hours in a day."""
        if value is None:
            return None
        if value < 0 or value > 23:
            raise ValueError("hour must be between 0 and 23")
        return value

    @field_validator("weekdays")
    @classmethod
    def normalize_weekdays(
        cls,
        value: list[StockResearchScheduleWeekday],
    ) -> list[StockResearchScheduleWeekday]:
        """Deduplicate persisted weekdays while preserving request order."""
        return list(dict.fromkeys(value))

    @field_validator("next_run_at", "created_at", "updated_at")
    @classmethod
    def normalize_utc_datetime(cls, value: datetime) -> datetime:
        """Persist schedule datetimes as timezone-aware UTC values."""
        return _normalize_utc_datetime(value)


class StockResearchScheduleRun(StockResearchScheduleModelBase):
    """One idempotent occurrence dispatch record for a stock research schedule."""

    id: str | None = Field(default=None, alias="_id")
    schedule_id: str
    occurrence_at: datetime
    status: StockResearchScheduleRunStatus = (
        StockResearchScheduleRunStatus.DISPATCHING
    )
    report_id: str | None = None
    lock_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("schedule_id", "report_id", mode="before")
    @classmethod
    def normalize_optional_identifier(cls, value: str | None) -> str | None:
        """Require persisted identifiers to be non-blank when present."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifiers must not be blank")
        return normalized

    @field_validator("occurrence_at", "lock_expires_at", "created_at", "updated_at")
    @classmethod
    def normalize_optional_utc_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        """Persist occurrence datetimes as timezone-aware UTC values."""
        if value is None:
            return None
        return _normalize_utc_datetime(value)


def _normalize_utc_datetime(value: datetime) -> datetime:
    """Normalize one aware datetime to UTC for durable scheduler comparisons."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)
