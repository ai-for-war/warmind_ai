"""Upstream gateway for loading KBS stock financial report data from vnstock."""

from __future__ import annotations

from collections.abc import Callable
import math
from typing import Any

from app.config.settings import get_settings
from app.domain.schemas.stock_financial_report import (
    StockFinancialReportPeriod,
    StockFinancialReportType,
)

FINANCIAL_REPORT_METHODS: dict[str, str] = {
    StockFinancialReportType.INCOME_STATEMENT.value: "income_statement",
    StockFinancialReportType.BALANCE_SHEET.value: "balance_sheet",
    StockFinancialReportType.CASH_FLOW.value: "cash_flow",
    StockFinancialReportType.RATIO.value: "ratio",
}

NON_PERIOD_FIELDS: tuple[str, ...] = (
    "item",
    "item_id",
    "item_en",
    "unit",
    "levels",
    "row_number",
)


class VnstockFinancialReportGateway:
    """Thin wrapper around vnstock Finance(source='KBS') financial reports."""

    SOURCE = "KBS"

    def __init__(
        self,
        *,
        finance_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._finance_factory = finance_factory
        if finance_factory is not None:
            return

        from vnstock import register_user

        settings = get_settings()
        register_user(api_key=settings.VNSTOCK_API_KEY)

    def fetch_report(
        self,
        symbol: str,
        *,
        report_type: StockFinancialReportType | str,
        period: StockFinancialReportPeriod | str,
    ) -> dict[str, Any]:
        """Fetch and normalize one KBS financial report table."""
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_report_type = self._normalize_report_type(report_type)
        normalized_period = self._normalize_period(period)

        finance = self._build_finance(normalized_symbol)
        method = getattr(finance, FINANCIAL_REPORT_METHODS[normalized_report_type])
        # Installed vnstock 4.0.2 exposes `display_mode` and `include_metadata`
        # in the KBS provider source, but those kwargs are not reliably accepted
        # through the public Finance adapter for income_statement, balance_sheet,
        # and cash_flow. Call the public runtime path with only `period` and keep
        # v1 rows to the stable `item`/`item_id` columns plus period values.
        payload = method(period=normalized_period)

        normalized_payload = self._to_report_payload(payload)
        return {
            "symbol": normalized_symbol,
            "source": self.SOURCE,
            "report_type": normalized_report_type,
            "period": normalized_period,
            **normalized_payload,
        }

    def _build_finance(self, symbol: str) -> Any:
        normalized_symbol = self._normalize_symbol(symbol)

        if self._finance_factory is not None:
            return self._finance_factory(normalized_symbol, self.SOURCE)

        from vnstock import Finance

        return Finance(symbol=normalized_symbol, source=self.SOURCE)

    @classmethod
    def _to_report_payload(cls, payload: Any) -> dict[str, Any]:
        """Convert one vnstock financial report payload to periods and rows."""
        if payload is None:
            return {"periods": [], "items": []}

        periods = cls._extract_periods(payload)
        records = cls._to_records(payload)
        if not periods:
            periods = cls._infer_periods_from_records(records)

        items: list[dict[str, Any]] = []
        for record in records:
            item = cls._normalize_text(record.get("item"))
            if item is None:
                continue
            item_id = cls._normalize_item_id(record.get("item_id"))
            values = {
                period: cls._normalize_missing_value(record.get(period))
                for period in periods
            }
            items.append(
                {
                    "item": item,
                    "item_id": item_id,
                    "values": values,
                }
            )

        return {"periods": periods, "items": items}

    @staticmethod
    def _to_records(payload: Any) -> list[dict[str, Any]]:
        """Convert one DataFrame-like or list payload into record dicts."""
        if hasattr(payload, "empty") and payload.empty:
            return []
        if hasattr(payload, "to_dict"):
            records = payload.to_dict(orient="records")
        elif isinstance(payload, list):
            records = payload
        else:
            raise TypeError("Unsupported vnstock financial report payload type")

        return [record for record in records if isinstance(record, dict)]

    @classmethod
    def _extract_periods(cls, payload: Any) -> list[str]:
        """Read period labels in provider order when the payload exposes them."""
        attrs = getattr(payload, "attrs", None)
        attr_periods = attrs.get("periods") if isinstance(attrs, dict) else None
        if isinstance(attr_periods, list):
            return [str(period) for period in attr_periods if period is not None]

        columns = getattr(payload, "columns", None)
        if columns is None:
            return []
        return [
            str(column)
            for column in list(columns)
            if str(column) not in NON_PERIOD_FIELDS
        ]

    @staticmethod
    def _infer_periods_from_records(records: list[dict[str, Any]]) -> list[str]:
        """Infer period label order from record key order when no columns exist."""
        periods: list[str] = []
        for record in records:
            for key in record:
                period = str(key)
                if period in NON_PERIOD_FIELDS or period in periods:
                    continue
                periods.append(period)
        return periods

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be blank")
        return normalized_symbol

    @staticmethod
    def _normalize_report_type(report_type: StockFinancialReportType | str) -> str:
        if isinstance(report_type, StockFinancialReportType):
            return report_type.value
        if not isinstance(report_type, str):
            raise TypeError("report_type must be a string")
        normalized = report_type.strip().lower()
        if normalized not in FINANCIAL_REPORT_METHODS:
            raise ValueError("unsupported financial report type")
        return normalized

    @staticmethod
    def _normalize_period(period: StockFinancialReportPeriod | str) -> str:
        if isinstance(period, StockFinancialReportPeriod):
            return period.value
        if not isinstance(period, str):
            raise TypeError("period must be a string")
        normalized = period.strip().lower()
        supported_periods = {period.value for period in StockFinancialReportPeriod}
        if normalized not in supported_periods:
            raise ValueError("unsupported financial report period")
        return normalized

    @staticmethod
    def _normalize_text(value: Any) -> str | None:
        normalized = VnstockFinancialReportGateway._normalize_missing_value(value)
        if normalized is None:
            return None
        text = str(normalized).strip()
        return text or None

    @staticmethod
    def _normalize_item_id(value: Any) -> str | int | None:
        normalized = VnstockFinancialReportGateway._normalize_missing_value(value)
        if normalized is None:
            return None
        if isinstance(normalized, bool):
            return int(normalized)
        if isinstance(normalized, int):
            return normalized
        if isinstance(normalized, float) and normalized.is_integer():
            return int(normalized)
        text = str(normalized).strip()
        return text or None

    @staticmethod
    def _normalize_missing_value(value: Any) -> Any:
        # The installed vnstock runtime materializes missing DataFrame cells as
        # NaN in record dicts. Collapse them to `None` so financial cells remain
        # JSON-compatible and stable across report types.
        try:
            if math.isnan(value):
                return None
        except (TypeError, ValueError):
            pass
        return value
