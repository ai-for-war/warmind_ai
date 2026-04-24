"""Durable stock research report persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StockResearchReportStatus(str, Enum):
    """Lifecycle states for one persisted stock research report."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class StockResearchReportModelBase(BaseModel):
    """Common persistence model settings for stock research report documents."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class StockResearchReportSource(StockResearchReportModelBase):
    """One web-source citation stored with a stock research report."""

    source_id: str
    url: str
    title: str

    @field_validator("source_id", "url", "title", mode="before")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        """Require persisted source metadata fields to be non-blank strings."""
        if not isinstance(value, str):
            raise TypeError("source fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("source fields must not be blank")
        return normalized


class StockResearchReportFailure(StockResearchReportModelBase):
    """Failure details stored for an unsuccessful stock research report."""

    code: str
    message: str

    @field_validator("code", "message", mode="before")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        """Require persisted failure details to be non-blank strings."""
        if not isinstance(value, str):
            raise TypeError("failure fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("failure fields must not be blank")
        return normalized


class StockResearchReportRuntimeConfig(StockResearchReportModelBase):
    """Resolved agent runtime configuration persisted with one report."""

    provider: str
    model: str
    reasoning: str | None = None

    @field_validator("provider", "model", mode="before")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        """Require persisted runtime identity fields to be non-blank strings."""
        if not isinstance(value, str):
            raise TypeError("runtime config fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("runtime config fields must not be blank")
        return normalized

    @field_validator("reasoning", mode="before")
    @classmethod
    def normalize_optional_reasoning(cls, value: str | None) -> str | None:
        """Collapse blank optional reasoning values to null."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("runtime reasoning must be a string or None")
        normalized = value.strip()
        return normalized or None


class StockResearchReport(StockResearchReportModelBase):
    """One persisted stock research report document stored in MongoDB."""

    id: str | None = Field(default=None, alias="_id")
    user_id: str
    organization_id: str
    symbol: str
    status: StockResearchReportStatus = StockResearchReportStatus.QUEUED
    runtime_config: StockResearchReportRuntimeConfig | None = None
    content: str | None = None
    sources: list[StockResearchReportSource] = Field(default_factory=list)
    error: StockResearchReportFailure | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
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
        """Persist stock symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("content", mode="before")
    @classmethod
    def normalize_optional_content(cls, value: str | None) -> str | None:
        """Collapse blank markdown content to null for stable persistence."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("content must be a string or None")
        normalized = value.strip()
        return normalized or None
