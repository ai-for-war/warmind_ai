"""Upstream gateway for loading stock price data from vnstock Quote."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
import math
from typing import Any

from app.config.settings import get_settings
from app.domain.schemas.stock_price import (
    DEFAULT_HISTORY_INTERVAL,
    DEFAULT_HISTORY_SOURCE,
    DEFAULT_INTRADAY_PAGE_SIZE,
    DEFAULT_INTRADAY_SOURCE,
    StockPriceSource,
)

HISTORY_FIELDS: tuple[str, ...] = (
    "time",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
INTRADAY_FIELDS: tuple[str, ...] = (
    "time",
    "price",
    "volume",
    "match_type",
    "id",
)


class VnstockPriceGateway:
    """Thin wrapper around vnstock Quote for supported price sources."""

    HISTORY_SOURCE = DEFAULT_HISTORY_SOURCE
    INTRADAY_SOURCE = DEFAULT_INTRADAY_SOURCE

    def __init__(
        self,
        *,
        quote_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._quote_factory = quote_factory
        if quote_factory is not None:
            return

        from vnstock import register_user

        settings = get_settings()
        register_user(api_key=settings.VNSTOCK_API_KEY)

    def fetch_history(
        self,
        symbol: str,
        *,
        source: StockPriceSource = HISTORY_SOURCE,
        start: str | None = None,
        end: str | None = None,
        interval: str = DEFAULT_HISTORY_INTERVAL,
        length: int | str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch historical OHLCV timeseries for one stock symbol."""
        payload = self._build_quote(symbol, source=source).history(
            start=start,
            end=end,
            interval=interval,
            length=length,
        )
        return self._to_records(
            payload,
            allowed_fields=HISTORY_FIELDS,
            transform_record=self._normalize_history_record,
        )

    def fetch_intraday(
        self,
        symbol: str,
        *,
        source: StockPriceSource = INTRADAY_SOURCE,
        page_size: int = DEFAULT_INTRADAY_PAGE_SIZE,
        last_time: str | None = None,
        last_time_format: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch intraday trade timeseries for one stock symbol."""
        intraday_kwargs: dict[str, Any] = {"page_size": page_size}
        if source == "VCI":
            intraday_kwargs.update(
                {
                    "last_time": last_time,
                    "last_time_format": last_time_format,
                }
            )
        quote = self._build_quote(symbol, source=source)
        intraday_method = getattr(quote, "provider", quote).intraday
        payload = intraday_method(**intraday_kwargs)
        return self._to_records(
            payload,
            allowed_fields=INTRADAY_FIELDS,
            transform_record=self._normalize_intraday_record,
        )

    def _build_quote(
        self,
        symbol: str,
        *,
        source: StockPriceSource = DEFAULT_INTRADAY_SOURCE,
    ) -> Any:
        normalized_symbol = self._normalize_symbol(symbol)

        if self._quote_factory is not None:
            return self._quote_factory(normalized_symbol, source)

        from vnstock import Quote

        # The public Quote wrapper currently advertises broader compatibility
        # parameters like `resolution` and `page`, but the installed runtime path
        # we depend on uses `history(start, end, interval, ..., length)` for VCI
        # and KBS. Intraday cursor handling remains source-specific in service.
        return Quote(symbol=normalized_symbol, source=source)

    @classmethod
    def _to_records(
        cls,
        payload: Any,
        *,
        allowed_fields: tuple[str, ...],
        transform_record: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Convert one vnstock price payload to a normalized record list."""
        if payload is None:
            return []
        if hasattr(payload, "to_dict"):
            records = payload.to_dict(orient="records")
        elif isinstance(payload, list):
            records = payload
        else:
            raise TypeError("Unsupported vnstock price payload type")

        normalized: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            normalized_record = {
                key: cls._normalize_missing_value(record[key])
                for key in allowed_fields
                if key in record
            }
            if transform_record is not None:
                normalized_record = transform_record(normalized_record)
            normalized.append(normalized_record)
        return normalized

    @classmethod
    def _normalize_history_record(cls, record: dict[str, Any]) -> dict[str, Any]:
        """Normalize one history row to the public canonical payload."""
        normalized = dict(record)
        normalized["time"] = cls._normalize_time_value(normalized.get("time"))
        return normalized

    @classmethod
    def _normalize_intraday_record(cls, record: dict[str, Any]) -> dict[str, Any]:
        """Normalize one intraday row to the public canonical payload."""
        normalized = dict(record)
        normalized["time"] = cls._normalize_time_value(normalized.get("time"))
        normalized["id"] = cls._normalize_identifier_value(normalized.get("id"))
        return normalized

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be blank")
        return normalized_symbol

    @staticmethod
    def _normalize_missing_value(value: Any) -> Any:
        # The installed vnstock runtime materializes missing DataFrame cells as
        # NaN in record dicts. Collapse them to `None` so the API contract stays
        # stable across empty numeric/string cells.
        try:
            if math.isnan(value):
                return None
        except (TypeError, ValueError):
            pass
        return value

    @classmethod
    def _normalize_time_value(cls, value: Any) -> str | None:
        """Serialize date-like values to stable strings for API transport."""
        normalized = cls._normalize_missing_value(value)
        if normalized is None:
            return None
        if hasattr(normalized, "to_pydatetime"):
            normalized = normalized.to_pydatetime()
        if isinstance(normalized, datetime):
            return normalized.isoformat(timespec="seconds")
        if isinstance(normalized, date):
            return normalized.isoformat()
        return str(normalized)

    @classmethod
    def _normalize_identifier_value(cls, value: Any) -> int | str | None:
        """Preserve provider-compatible intraday identifiers."""
        normalized = cls._normalize_missing_value(value)
        if normalized is None:
            return None
        if isinstance(normalized, bool):
            return int(normalized)
        if isinstance(normalized, int):
            return normalized
        if isinstance(normalized, float):
            return int(normalized)
        if isinstance(normalized, str):
            stripped = normalized.strip()
            if not stripped:
                return None
            return int(stripped) if stripped.isdigit() else stripped
        raise TypeError("Unsupported intraday identifier type")
