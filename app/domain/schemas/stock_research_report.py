"""Schemas for stock research report request and response payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.domain.models.stock_research_report import StockResearchReportStatus
from app.domain.schemas.stock import StockSchemaBase

MAX_STOCK_RESEARCH_SYMBOL_LENGTH = 32


class StockResearchReportSchemaBase(StockSchemaBase):
    """Base schema for stock research report transport payloads."""


class StockResearchReportCreateRequest(StockResearchReportSchemaBase):
    """Request payload for creating one stock research report."""

    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize requested symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class StockResearchReportSourceResponse(StockResearchReportSchemaBase):
    """One stored source item returned by stock research report APIs."""

    source_id: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)


class StockResearchReportFailureResponse(StockResearchReportSchemaBase):
    """Failure details returned for an unsuccessful stock research report."""

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class StockResearchReportSummary(StockResearchReportSchemaBase):
    """Common stock research report fields returned by create, get, and list APIs."""

    id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    status: StockResearchReportStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize response symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class StockResearchReportCreateResponse(StockResearchReportSummary):
    """Accepted-response payload returned after creating a report job."""


class StockResearchReportResponse(StockResearchReportSummary):
    """Full stock research report payload for read operations."""

    content: str | None = None
    sources: list[StockResearchReportSourceResponse] = Field(default_factory=list)
    error: StockResearchReportFailureResponse | None = None


class StockResearchReportListResponse(StockResearchReportSchemaBase):
    """Response returned by the stock research report history endpoint."""

    items: list[StockResearchReportSummary] = Field(default_factory=list)
