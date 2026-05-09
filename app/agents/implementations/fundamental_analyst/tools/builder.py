"""Tool surface builder for the fundamental analyst runtime."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from app.agents.implementations.fundamental_analyst.tools.company_profile import (
    load_company_profile,
)
from app.agents.implementations.fundamental_analyst.tools.financial_reports import (
    load_balance_sheet,
    load_cash_flow,
    load_financial_ratios,
    load_income_statement,
)


@dataclass(frozen=True)
class FundamentalAnalystToolSurface:
    """Resolved deterministic tools used by the fundamental analyst runtime."""

    load_company_profile: BaseTool
    load_income_statement: BaseTool
    load_balance_sheet: BaseTool
    load_cash_flow: BaseTool
    load_financial_ratios: BaseTool
    tools: tuple[BaseTool, BaseTool, BaseTool, BaseTool, BaseTool]


def get_fundamental_analyst_tool_surface() -> FundamentalAnalystToolSurface:
    """Return exactly the five phase-one fundamental-analysis tools."""
    return FundamentalAnalystToolSurface(
        load_company_profile=load_company_profile,
        load_income_statement=load_income_statement,
        load_balance_sheet=load_balance_sheet,
        load_cash_flow=load_cash_flow,
        load_financial_ratios=load_financial_ratios,
        tools=(
            load_company_profile,
            load_income_statement,
            load_balance_sheet,
            load_cash_flow,
            load_financial_ratios,
        ),
    )

