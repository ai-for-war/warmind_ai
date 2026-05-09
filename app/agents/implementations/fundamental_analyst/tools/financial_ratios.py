"""Financial ratios tool for the fundamental analyst runtime."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from app.agents.implementations.fundamental_analyst.tools.report_loader import (
    load_financial_report_result,
)
from app.agents.implementations.fundamental_analyst.tools.schemas import (
    LoadFinancialReportInput,
)
from app.domain.schemas.stock_financial_report import StockFinancialReportType
from app.services.stocks.financial_report_service import StockFinancialReportService


async def load_financial_ratios_result(
    request: LoadFinancialReportInput | dict[str, Any],
    *,
    stock_financial_report_service: StockFinancialReportService | None = None,
) -> dict[str, Any]:
    """Load KBS Finance.ratio data."""
    return await load_financial_report_result(
        request,
        report_type=StockFinancialReportType.RATIO,
        tool_name="load_financial_ratios",
        stock_financial_report_service=stock_financial_report_service,
    )


async def _load_financial_ratios_tool(**kwargs: Any) -> dict[str, Any]:
    return await load_financial_ratios_result(kwargs)


load_financial_ratios = StructuredTool.from_function(
    coroutine=_load_financial_ratios_tool,
    name="load_financial_ratios",
    description=(
        "Load KBS Finance.ratio items through StockFinancialReportService. "
        "Do not substitute VCI ratio_summary. Defaults to quarterly data and accepts "
        "period='year'."
    ),
    args_schema=LoadFinancialReportInput,
)

