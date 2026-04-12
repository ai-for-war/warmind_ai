"""Schemas for stock catalog request and response payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_STOCK_PAGE_SIZE = 20
MAX_STOCK_PAGE_SIZE = 100


class StockSchemaBase(BaseModel):
    """Base schema for stock catalog transport payloads."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class StockListQuery(StockSchemaBase):
    """Query parameters for paginated stock catalog reads."""

    q: str | None = None
    exchange: str | None = None
    group: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default=DEFAULT_STOCK_PAGE_SIZE,
        ge=1,
        le=MAX_STOCK_PAGE_SIZE,
    )

    @field_validator("q", mode="before")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        """Treat blank query text as absent."""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("exchange", "group", mode="before")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        """Normalize filter values to uppercase for stable querying."""
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None


class StockListItem(StockSchemaBase):
    """One stock symbol returned by the stock catalog API."""

    symbol: str = Field(..., min_length=1)
    organ_name: str | None = None
    exchange: str | None = None
    groups: list[str] = Field(default_factory=list)
    industry_code: int | None = None
    industry_name: str | None = None
    source: str = Field(default="VCI", min_length=1)
    snapshot_at: datetime
    updated_at: datetime


class StockListResponse(StockSchemaBase):
    """Paginated stock catalog response."""

    items: list[StockListItem]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)


class StockRefreshResponse(StockSchemaBase):
    """Response returned after a manual stock catalog refresh."""

    status: str = Field(..., min_length=1)
    source: str = Field(default="VCI", min_length=1)
    upserted: int = Field(..., ge=0)
    updated_at: datetime
