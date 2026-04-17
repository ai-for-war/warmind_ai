"""Schemas for stock watchlist request and response payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.domain.schemas.stock import StockSchemaBase

MAX_STOCK_WATCHLIST_NAME_LENGTH = 255
MAX_STOCK_SYMBOL_LENGTH = 32


class StockWatchlistSchemaBase(StockSchemaBase):
    """Base schema for stock watchlist transport payloads."""


class StockWatchlistOwnership(StockWatchlistSchemaBase):
    """Ownership scope attached to watchlist resources."""

    user_id: str = Field(..., min_length=1)
    organization_id: str = Field(..., min_length=1)


class StockWatchlistCreateRequest(StockWatchlistSchemaBase):
    """Request payload for creating a new watchlist."""

    name: str = Field(..., min_length=1, max_length=MAX_STOCK_WATCHLIST_NAME_LENGTH)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Require a non-blank watchlist display name."""
        if not isinstance(value, str):
            raise TypeError("name must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class StockWatchlistRenameRequest(StockWatchlistSchemaBase):
    """Request payload for renaming an existing watchlist."""

    name: str = Field(..., min_length=1, max_length=MAX_STOCK_WATCHLIST_NAME_LENGTH)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Require a non-blank watchlist display name."""
        if not isinstance(value, str):
            raise TypeError("name must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class StockWatchlistSummary(StockWatchlistOwnership):
    """Watchlist identity and ownership returned by watchlist APIs."""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=MAX_STOCK_WATCHLIST_NAME_LENGTH)
    created_at: datetime
    updated_at: datetime


class StockWatchlistListResponse(StockWatchlistSchemaBase):
    """Response returned by the watchlist list endpoint."""

    items: list[StockWatchlistSummary] = Field(default_factory=list)


class StockWatchlistDeleteResponse(StockWatchlistSchemaBase):
    """Response payload for successful watchlist deletion."""

    id: str = Field(..., min_length=1)
    deleted: bool = True


class StockWatchlistStockMetadata(StockWatchlistSchemaBase):
    """Latest persisted stock-catalog metadata merged onto one saved item."""

    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_SYMBOL_LENGTH)
    organ_name: str | None = None
    exchange: str | None = None
    groups: list[str] = Field(default_factory=list)
    industry_code: int | None = None
    industry_name: str | None = None
    source: str = Field(default="VCI", min_length=1)
    snapshot_at: datetime
    updated_at: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist response symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class StockWatchlistAddItemRequest(StockWatchlistSchemaBase):
    """Request payload for adding one stock symbol to a watchlist."""

    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_SYMBOL_LENGTH)

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


class StockWatchlistItemSummary(StockWatchlistOwnership):
    """Saved-item identity and timestamps returned by watchlist item APIs."""

    id: str = Field(..., min_length=1)
    watchlist_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_SYMBOL_LENGTH)
    saved_at: datetime
    updated_at: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist response symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class StockWatchlistItemResponse(StockWatchlistItemSummary):
    """Saved watchlist item merged with the latest stock catalog metadata."""

    stock: StockWatchlistStockMetadata | None = None


class StockWatchlistItemsResponse(StockWatchlistSchemaBase):
    """Response returned by the watchlist-items list endpoint."""

    watchlist: StockWatchlistSummary
    items: list[StockWatchlistItemResponse] = Field(default_factory=list)


class StockWatchlistRemoveItemResponse(StockWatchlistSchemaBase):
    """Response payload for successful watchlist-item removal."""

    watchlist_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_SYMBOL_LENGTH)
    removed: bool = True

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist removed symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized
