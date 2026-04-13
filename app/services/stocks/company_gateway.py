"""Upstream gateway for loading stock company data from vnstock VCI."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import math
from typing import Any

from app.config.settings import get_settings

OVERVIEW_FIELDS: tuple[str, ...] = (
    "symbol",
    "id",
    "issue_share",
    "history",
    "company_profile",
    "icb_name2",
    "icb_name3",
    "icb_name4",
    "charter_capital",
    "financial_ratio_issue_share",
)
SHAREHOLDER_FIELDS: tuple[str, ...] = (
    "id",
    "share_holder",
    "quantity",
    "share_own_percent",
    "update_date",
)
OFFICER_FIELDS: tuple[str, ...] = (
    "id",
    "officer_name",
    "officer_position",
    "position_short_name",
    "update_date",
    "officer_own_percent",
    "quantity",
    "type",
)
SUBSIDIARY_FIELDS: tuple[str, ...] = (
    "id",
    "sub_organ_code",
    "organ_name",
    "ownership_percent",
    "type",
)
AFFILIATE_FIELDS: tuple[str, ...] = (
    "id",
    "sub_organ_code",
    "organ_name",
    "ownership_percent",
)
EVENT_FIELDS: tuple[str, ...] = (
    "id",
    "event_title",
    "public_date",
    "issue_date",
    "source_url",
    "event_list_code",
    "ratio",
    "value",
    "record_date",
    "exright_date",
    "event_list_name",
)
NEWS_FIELDS: tuple[str, ...] = (
    "id",
    "news_title",
    "news_sub_title",
    "friendly_sub_title",
    "news_image_url",
    "news_source_link",
    "created_at",
    "public_date",
    "updated_at",
    "lang_code",
    "news_id",
    "news_short_content",
    "news_full_content",
    "close_price",
    "ref_price",
    "floor",
    "ceiling",
    "price_change_pct",
)
REPORT_FIELDS: tuple[str, ...] = (
    "date",
    "description",
    "link",
    "name",
)
RATIO_SUMMARY_FIELDS: tuple[str, ...] = (
    "symbol",
    "year_report",
    "length_report",
    "update_date",
    "revenue",
    "revenue_growth",
    "net_profit",
    "net_profit_growth",
    "roe",
    "roa",
    "pe",
    "pb",
    "eps",
    "issue_share",
    "charter_capital",
    "dividend",
    "de",
)
TRADING_STATS_FIELDS: tuple[str, ...] = (
    "symbol",
    "exchange",
    "ev",
    "ceiling",
    "floor",
    "ref_price",
    "open",
    "match_price",
    "close_price",
    "price_change",
    "price_change_pct",
    "high",
    "low",
    "total_volume",
    "high_price_1y",
    "low_price_1y",
    "pct_low_change_1y",
    "pct_high_change_1y",
    "foreign_volume",
    "foreign_room",
    "avg_match_volume_2w",
    "foreign_holding_room",
    "current_holding_ratio",
    "max_holding_ratio",
)


class VnstockCompanyGateway:
    """Thin wrapper around vnstock Company(source='VCI')."""

    SOURCE = "VCI"

    def __init__(
        self,
        *,
        company_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._company_factory = company_factory
        if company_factory is not None:
            return

        from vnstock import register_user

        settings = get_settings()
        register_user(api_key=settings.VNSTOCK_API_KEY)

    def fetch_overview(self, symbol: str) -> dict[str, Any]:
        """Fetch overview data for one stock symbol."""
        normalized_symbol = self._normalize_symbol(symbol)
        payload = self._build_company(symbol).overview()
        return self._to_single_record(
            payload,
            allowed_fields=OVERVIEW_FIELDS,
            empty_record={"symbol": normalized_symbol},
        )

    def fetch_shareholders(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch major shareholders for one stock symbol."""
        payload = self._build_company(symbol).shareholders()
        return self._to_records(payload, allowed_fields=SHAREHOLDER_FIELDS)

    def fetch_officers(
        self,
        symbol: str,
        *,
        filter_by: str = "working",
    ) -> list[dict[str, Any]]:
        """Fetch company officers for one stock symbol."""
        payload = self._build_company(symbol).officers(filter_by=filter_by)
        return self._to_records(payload, allowed_fields=OFFICER_FIELDS)

    def fetch_subsidiaries(
        self,
        symbol: str,
        *,
        filter_by: str = "all",
    ) -> list[dict[str, Any]]:
        """Fetch subsidiaries for one stock symbol."""
        payload = self._build_company(symbol).subsidiaries(filter_by=filter_by)
        return self._to_records(payload, allowed_fields=SUBSIDIARY_FIELDS)

    def fetch_affiliate(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch affiliates for one stock symbol."""
        payload = self._build_company(symbol).affiliate()
        return self._to_records(payload, allowed_fields=AFFILIATE_FIELDS)

    def fetch_events(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch company events for one stock symbol."""
        payload = self._build_company(symbol).events()
        return self._to_records(payload, allowed_fields=EVENT_FIELDS)

    def fetch_news(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch company news for one stock symbol."""
        payload = self._build_company(symbol).news()
        records = self._to_records(payload, allowed_fields=NEWS_FIELDS)
        # The installed VCI runtime currently returns `public_date` as a
        # millisecond timestamp in `news()` even though other company sections
        # already normalize date-like fields to strings. Stabilize the backend
        # contract here using the runtime currently installed.
        return self._normalize_timestamp_fields(
            records,
            field_names=("created_at", "public_date", "updated_at"),
        )

    def fetch_reports(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch company analysis reports for one stock symbol."""
        # The installed runtime delegates provider-only methods like `reports()`
        # even though the public wrapper class does not declare them explicitly.
        payload = self._build_company(symbol).reports()
        return self._to_records(payload, allowed_fields=REPORT_FIELDS)

    def fetch_ratio_summary(self, symbol: str) -> dict[str, Any]:
        """Fetch ratio-summary data for one stock symbol."""
        normalized_symbol = self._normalize_symbol(symbol)
        payload = self._build_company(symbol).ratio_summary()
        record = self._to_single_record(
            payload,
            allowed_fields=RATIO_SUMMARY_FIELDS,
            empty_record={"symbol": normalized_symbol},
        )
        normalized = self._normalize_timestamp_fields(
            [record],
            field_names=("update_date",),
        )
        return normalized[0] if normalized else {"symbol": normalized_symbol}

    def fetch_trading_stats(self, symbol: str) -> dict[str, Any]:
        """Fetch trading-stat snapshot data for one stock symbol."""
        normalized_symbol = self._normalize_symbol(symbol)
        payload = self._build_company(symbol).trading_stats()
        return self._to_single_record(
            payload,
            allowed_fields=TRADING_STATS_FIELDS,
            empty_record={"symbol": normalized_symbol},
        )

    def _build_company(self, symbol: str) -> Any:
        normalized_symbol = self._normalize_symbol(symbol)

        if self._company_factory is not None:
            return self._company_factory(normalized_symbol, self.SOURCE)

        from vnstock import Company

        return Company(symbol=normalized_symbol, source=self.SOURCE)

    @staticmethod
    def _to_records(
        payload: Any,
        *,
        allowed_fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        """Convert one vnstock section payload to a normalized record list."""
        if payload is None:
            return []
        if hasattr(payload, "to_dict"):
            records = payload.to_dict(orient="records")
        elif isinstance(payload, list):
            records = payload
        else:
            raise TypeError("Unsupported vnstock company payload type")

        normalized: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            normalized.append(
                {
                    key: VnstockCompanyGateway._normalize_missing_value(record[key])
                    for key in allowed_fields
                    if key in record
                }
            )
        return normalized

    @classmethod
    def _to_single_record(
        cls,
        payload: Any,
        *,
        allowed_fields: tuple[str, ...],
        empty_record: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convert one vnstock snapshot payload to one normalized record."""
        records = cls._to_records(payload, allowed_fields=allowed_fields)
        if not records:
            return dict(empty_record or {})
        return records[0]

    @staticmethod
    def _normalize_timestamp_fields(
        records: list[dict[str, Any]],
        *,
        field_names: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        """Convert millisecond timestamps in selected fields into UTC strings."""
        normalized: list[dict[str, Any]] = []
        for record in records:
            normalized_record = dict(record)
            for field_name in field_names:
                value = normalized_record.get(field_name)
                if isinstance(value, (int, float)):
                    normalized_record[field_name] = (
                        datetime.fromtimestamp(value / 1000, tz=timezone.utc)
                        .isoformat(timespec="seconds")
                        .replace("+00:00", "Z")
                    )
            normalized.append(normalized_record)
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
        # NaN in record dicts. Collapse them to `None` before Pydantic validation
        # so optional text/numeric fields stay stable across sections.
        try:
            if math.isnan(value):
                return None
        except (TypeError, ValueError):
            pass
        return value
