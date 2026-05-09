"""Shared KBS report loader for fundamental analyst financial tools."""

from __future__ import annotations

from typing import Any

from app.agents.implementations.fundamental_analyst.tools.dependencies import (
    get_stock_financial_report_service,
)
from app.agents.implementations.fundamental_analyst.tools.evidence import (
    build_bounded_failure_result,
    build_financial_report_tool_result,
    normalize_financial_period,
    normalize_symbol_for_tool,
)
from app.agents.implementations.fundamental_analyst.tools.schemas import (
    LoadFinancialReportInput,
)
from app.domain.schemas.stock_financial_report import (
    StockFinancialReportQuery,
    StockFinancialReportType,
)
from app.services.stocks.financial_report_service import StockFinancialReportService


async def load_financial_report_result(
    request: LoadFinancialReportInput | dict[str, Any],
    *,
    report_type: StockFinancialReportType,
    tool_name: str,
    stock_financial_report_service: StockFinancialReportService | None = None,
) -> dict[str, Any]:
    """Load one KBS report type through the shared financial service."""
    normalized_request = LoadFinancialReportInput.model_validate(request)
    symbol = _safe_symbol(normalized_request.symbol)
    period: str | None = None
    try:
        symbol = normalize_symbol_for_tool(normalized_request.symbol)
        period = normalize_financial_period(normalized_request.period)
        service = stock_financial_report_service or get_stock_financial_report_service()
        response = await service.get_report(
            symbol,
            report_type,
            StockFinancialReportQuery(period=period),
        )
    except Exception as exc:
        return build_bounded_failure_result(
            symbol=symbol,
            source="KBS",
            tool_name=tool_name,
            report_type=report_type.value,
            period=period,
            exc=exc,
        )

    return build_financial_report_tool_result(response)


def _safe_symbol(value: str) -> str | None:
    try:
        return normalize_symbol_for_tool(value)
    except Exception:
        return None

