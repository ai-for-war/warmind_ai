"""Cash flow tool for the fundamental analyst runtime."""

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


async def load_cash_flow_result(
    request: LoadFinancialReportInput | dict[str, Any],
    *,
    stock_financial_report_service: StockFinancialReportService | None = None,
) -> dict[str, Any]:
    """Load KBS cash flow statement data."""
    return await load_financial_report_result(
        request,
        report_type=StockFinancialReportType.CASH_FLOW,
        tool_name="load_cash_flow",
        stock_financial_report_service=stock_financial_report_service,
    )


async def _load_cash_flow_tool(**kwargs: Any) -> dict[str, Any]:
    return await load_cash_flow_result(kwargs)


load_cash_flow = StructuredTool.from_function(
    coroutine=_load_cash_flow_tool,
    name="load_cash_flow",
    description=(
        "Load KBS cash flow items through StockFinancialReportService. "
        "Defaults to quarterly data and accepts period='year'."
    ),
    args_schema=LoadFinancialReportInput,
)

