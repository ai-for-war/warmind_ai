"""Shared helpers for fundamental analyst tools."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.domain.schemas.stock_financial_report import (
    DEFAULT_STOCK_FINANCIAL_REPORT_PERIOD,
    StockFinancialReportPeriod,
    StockFinancialReportResponse,
)


def normalize_symbol_for_tool(symbol: str) -> str:
    """Normalize a tool symbol argument for metadata and validation messages."""
    if not isinstance(symbol, str):
        raise TypeError("symbol must be a string")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be blank")
    return normalized


def normalize_financial_period(period: str | None) -> str:
    """Normalize supported financial periods before any upstream service read."""
    if period is None:
        return DEFAULT_STOCK_FINANCIAL_REPORT_PERIOD.value
    if not isinstance(period, str):
        raise TypeError("period must be a string")
    normalized = period.strip().lower() or DEFAULT_STOCK_FINANCIAL_REPORT_PERIOD.value
    supported_periods = {item.value for item in StockFinancialReportPeriod}
    if normalized not in supported_periods:
        raise ValueError("Unsupported financial report period")
    return normalized


def build_financial_report_tool_result(
    response: StockFinancialReportResponse,
) -> dict[str, Any]:
    """Return the KBS service payload shape without remapping report rows."""
    return {
        "symbol": response.symbol,
        "source": response.source,
        "report_type": response.report_type,
        "period": response.period,
        "periods": list(response.periods),
        "items": [item.model_dump(mode="json") for item in response.items],
        "data_gaps": [],
    }


def build_bounded_failure_result(
    *,
    symbol: str | None,
    source: str,
    tool_name: str,
    report_type: str | None = None,
    period: str | None = None,
    payload_key: str = "items",
    exc: Exception,
) -> dict[str, Any]:
    """Convert tool failures into data gaps the analyst can preserve."""
    detail = _exception_detail(exc)
    return {
        "symbol": symbol,
        "source": source,
        "tool_name": tool_name,
        "report_type": report_type,
        "period": period,
        payload_key: [] if payload_key == "items" else None,
        "data_gaps": [detail],
        "error": {
            "type": exc.__class__.__name__,
            "detail": detail,
        },
    }


def _exception_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    message = str(exc).strip()
    return message or "Fundamental evidence tool failed."
