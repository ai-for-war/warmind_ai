"""Durable stock watchlist persistence models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StockWatchlistModelBase(BaseModel):
    """Common persistence model settings for watchlist documents."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class StockWatchlist(StockWatchlistModelBase):
    """One user-owned stock watchlist document stored in MongoDB."""

    id: str | None = Field(default=None, alias="_id")
    user_id: str
    organization_id: str
    name: str
    normalized_name: str | None = None
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

    @model_validator(mode="after")
    def populate_derived_fields(self) -> "StockWatchlist":
        """Backfill stable normalized fields for repository querying."""
        self.normalized_name = (self.normalized_name or self.name).strip().lower()
        return self


class StockWatchlistItem(StockWatchlistModelBase):
    """One saved stock symbol inside a user-owned watchlist."""

    id: str | None = Field(default=None, alias="_id")
    watchlist_id: str
    user_id: str
    organization_id: str
    symbol: str
    normalized_symbol: str | None = None
    saved_at: datetime
    updated_at: datetime

    @field_validator(
        "watchlist_id",
        "user_id",
        "organization_id",
        mode="before",
    )
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        """Require non-blank watchlist and ownership identifiers."""
        if not isinstance(value, str):
            raise TypeError("identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifiers must not be blank")
        return normalized

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist saved stock symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @model_validator(mode="after")
    def populate_derived_fields(self) -> "StockWatchlistItem":
        """Backfill stable normalized fields for repository querying."""
        self.normalized_symbol = (
            self.normalized_symbol or self.symbol
        ).strip().lower()
        return self
