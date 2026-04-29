"""Schemas for stock price history and intraday request/response payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.domain.schemas.stock import StockSchemaBase

StockPriceSource = Literal["VCI", "KBS"]
HistoryInterval = Literal["1m", "5m", "15m", "30m", "1H", "1D", "1W", "1M"]

DEFAULT_HISTORY_INTERVAL: HistoryInterval = "1D"
DEFAULT_INTRADAY_PAGE_SIZE = 100
MAX_INTRADAY_PAGE_SIZE = 30_000


class StockPriceQueryBase(StockSchemaBase):
    """Base schema for stock price query parameters."""

    source: StockPriceSource = "VCI"

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: str | None) -> StockPriceSource:
        """Normalize source text to the supported vnstock source values."""
        if value is None:
            return "VCI"
        if not isinstance(value, str):
            raise TypeError("source must be a string")
        normalized = value.strip().upper()
        return normalized or "VCI"  # type: ignore[return-value]


class StockPriceHistoryQuery(StockPriceQueryBase):
    """Public query parameters for the stock price history endpoint."""

    start: str | None = None
    end: str | None = None
    interval: HistoryInterval = DEFAULT_HISTORY_INTERVAL
    length: int | str | None = None

    @field_validator("start", "end", mode="before")
    @classmethod
    def normalize_optional_datetime_text(cls, value: str | None) -> str | None:
        """Treat blank date or datetime input as absent."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("datetime query values must be strings")
        normalized = value.strip()
        return normalized or None

    @field_validator("interval", mode="before")
    @classmethod
    def normalize_interval(cls, value: str | None) -> HistoryInterval:
        """Normalize interval text into the canonical vnstock value."""
        if value is None:
            return DEFAULT_HISTORY_INTERVAL
        if not isinstance(value, str):
            raise TypeError("interval must be a string")
        normalized = value.strip()
        if not normalized:
            return DEFAULT_HISTORY_INTERVAL
        if normalized.endswith("m"):
            return normalized  # type: ignore[return-value]
        return normalized.upper()  # type: ignore[return-value]

    @field_validator("length", mode="before")
    @classmethod
    def normalize_length(cls, value: int | str | None) -> int | str | None:
        """Normalize lookback length while preserving supported vnstock forms."""
        if value is None or value == "":
            return None
        if isinstance(value, int):
            if value <= 0:
                raise ValueError("length must be greater than zero")
            return value
        if not isinstance(value, str):
            raise TypeError("length must be an int, str, or None")
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.isdigit():
            parsed = int(normalized)
            if parsed <= 0:
                raise ValueError("length must be greater than zero")
            return parsed
        return normalized.upper()

    @model_validator(mode="after")
    def validate_history_mode(self) -> "StockPriceHistoryQuery":
        """Require exactly one history read mode: explicit range or lookback."""
        has_start = self.start is not None
        has_length = self.length is not None
        if has_start == has_length:
            raise ValueError("provide exactly one of 'start' or 'length'")
        if self.end is not None and not has_start:
            raise ValueError("'end' is only allowed when 'start' is provided")
        return self


class StockPriceIntradayQuery(StockPriceQueryBase):
    """Public query parameters for the stock price intraday endpoint."""

    page_size: int = Field(
        default=DEFAULT_INTRADAY_PAGE_SIZE, ge=1, le=MAX_INTRADAY_PAGE_SIZE
    )
    last_time: str | None = None
    last_time_format: str | None = None

    @field_validator("last_time", "last_time_format", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Treat blank intraday cursor values as absent."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("intraday cursor values must be strings")
        normalized = value.strip()
        return normalized or None


class StockPriceResponseBase(StockSchemaBase):
    """Common response metadata for stock price payloads."""

    symbol: str = Field(..., min_length=1)
    source: StockPriceSource = "VCI"
    cache_hit: bool = False

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

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: str | None) -> StockPriceSource:
        """Normalize response source text to the supported vnstock source values."""
        if value is None:
            return "VCI"
        if not isinstance(value, str):
            raise TypeError("source must be a string")
        normalized = value.strip().upper()
        return normalized or "VCI"  # type: ignore[return-value]


class StockPriceHistoryItem(StockSchemaBase):
    """Canonical OHLCV row for one historical timestamp."""

    time: str | None = None
    open: int | float | None = None
    high: int | float | None = None
    low: int | float | None = None
    close: int | float | None = None
    volume: int | float | None = None


class StockPriceIntradayItem(StockSchemaBase):
    """Canonical intraday trade row for one timestamp."""

    time: str | None = None
    price: int | float | None = None
    volume: int | float | None = None
    match_type: str | None = None
    id: int | str | None = None


class StockPriceHistoryResponse(StockPriceResponseBase):
    """Response envelope for historical stock price reads."""

    interval: HistoryInterval = DEFAULT_HISTORY_INTERVAL
    items: list[StockPriceHistoryItem]


class StockPriceIntradayResponse(StockPriceResponseBase):
    """Response envelope for intraday stock price reads."""

    items: list[StockPriceIntradayItem]
