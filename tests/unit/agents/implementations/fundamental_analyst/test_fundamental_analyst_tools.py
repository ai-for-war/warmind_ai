from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agents.implementations.fundamental_analyst.tools.balance_sheet import (
    load_balance_sheet_result,
)
from app.agents.implementations.fundamental_analyst.tools.builder import (
    get_fundamental_analyst_tool_surface,
)
from app.agents.implementations.fundamental_analyst.tools.cash_flow import (
    load_cash_flow_result,
)
from app.agents.implementations.fundamental_analyst.tools.company_profile import (
    load_company_profile_result,
)
from app.agents.implementations.fundamental_analyst.tools.financial_ratios import (
    load_financial_ratios_result,
)
from app.agents.implementations.fundamental_analyst.tools.income_statement import (
    load_income_statement_result,
)
from app.domain.schemas.stock_company import (
    StockCompanyOverviewItem,
    StockCompanyOverviewResponse,
)
from app.domain.schemas.stock_financial_report import (
    StockFinancialReportItem,
    StockFinancialReportQuery,
    StockFinancialReportResponse,
    StockFinancialReportType,
)


class _FakeStockCompanyService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_overview(self, symbol: str) -> StockCompanyOverviewResponse:
        self.calls.append(symbol)
        return StockCompanyOverviewResponse(
            symbol=symbol,
            source="VCI",
            fetched_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
            cache_hit=True,
            item=StockCompanyOverviewItem(
                symbol=symbol,
                company_profile="Technology services company.",
                icb_name2="Technology",
                charter_capital=1_000_000,
                issue_share=100_000,
            ),
        )


class _FakeStockFinancialReportService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, StockFinancialReportType | str, str]] = []

    async def get_report(
        self,
        symbol: str,
        report_type: StockFinancialReportType | str,
        query: StockFinancialReportQuery,
    ) -> StockFinancialReportResponse:
        self.calls.append((symbol, report_type, query.period))
        return StockFinancialReportResponse(
            symbol=symbol,
            source="KBS",
            report_type=report_type,
            period=query.period,
            periods=["Q1 2026"],
            cache_hit=True,
            items=[
                StockFinancialReportItem(
                    item="Revenue",
                    item_id="revenue",
                    values={"Q1 2026": 100},
                )
            ],
        )


def test_fundamental_analyst_tool_surface_exposes_only_phase_one_tools() -> None:
    surface = get_fundamental_analyst_tool_surface()

    assert [tool.name for tool in surface.tools] == [
        "load_company_profile",
        "load_income_statement",
        "load_balance_sheet",
        "load_cash_flow",
        "load_financial_ratios",
    ]
    assert "delegate_tasks" not in {tool.name for tool in surface.tools}
    assert "load_skill" not in {tool.name for tool in surface.tools}
    assert "compute_technical_indicators" not in {tool.name for tool in surface.tools}


@pytest.mark.asyncio
async def test_load_company_profile_uses_vci_overview_service_path() -> None:
    service = _FakeStockCompanyService()

    result = await load_company_profile_result(
        {"symbol": " fpt "},
        stock_company_service=service,  # type: ignore[arg-type]
    )

    assert service.calls == ["FPT"]
    assert result["symbol"] == "FPT"
    assert result["source"] == "VCI"
    assert result["item"]["symbol"] == "FPT"
    assert result["item"]["company_profile"] == "Technology services company."
    assert result["data_gaps"] == []
    assert "status" not in result
    assert "fetched_at" not in result
    assert "cache_hit" not in result


@pytest.mark.parametrize(
    ("loader", "expected_report_type"),
    [
        (load_income_statement_result, StockFinancialReportType.INCOME_STATEMENT),
        (load_balance_sheet_result, StockFinancialReportType.BALANCE_SHEET),
        (load_cash_flow_result, StockFinancialReportType.CASH_FLOW),
        (load_financial_ratios_result, StockFinancialReportType.RATIO),
    ],
)
@pytest.mark.asyncio
async def test_financial_report_tools_use_kbs_service_default_quarter_and_raw_items(
    loader,
    expected_report_type: StockFinancialReportType,
) -> None:
    service = _FakeStockFinancialReportService()

    result = await loader(
        {"symbol": " fpt "},
        stock_financial_report_service=service,  # type: ignore[arg-type]
    )

    assert service.calls == [("FPT", expected_report_type, "quarter")]
    assert result["symbol"] == "FPT"
    assert result["source"] == "KBS"
    assert result["report_type"] == expected_report_type.value
    assert result["period"] == "quarter"
    assert result["periods"] == ["Q1 2026"]
    assert result["items"] == [
        {
            "item": "Revenue",
            "item_id": "revenue",
            "values": {"Q1 2026": 100},
        }
    ]
    assert result["data_gaps"] == []
    assert "status" not in result
    assert "cache_hit" not in result


@pytest.mark.parametrize(
    ("loader", "expected_report_type"),
    [
        (load_income_statement_result, StockFinancialReportType.INCOME_STATEMENT),
        (load_balance_sheet_result, StockFinancialReportType.BALANCE_SHEET),
        (load_cash_flow_result, StockFinancialReportType.CASH_FLOW),
        (load_financial_ratios_result, StockFinancialReportType.RATIO),
    ],
)
@pytest.mark.asyncio
async def test_financial_report_tools_accept_annual_override(
    loader,
    expected_report_type: StockFinancialReportType,
) -> None:
    service = _FakeStockFinancialReportService()

    result = await loader(
        {"symbol": "FPT", "period": " Year "},
        stock_financial_report_service=service,  # type: ignore[arg-type]
    )

    assert service.calls == [("FPT", expected_report_type, "year")]
    assert result["period"] == "year"


@pytest.mark.asyncio
async def test_financial_report_tool_rejects_unsupported_period_before_service_read() -> None:
    service = _FakeStockFinancialReportService()

    result = await load_income_statement_result(
        {"symbol": "FPT", "period": "month"},
        stock_financial_report_service=service,  # type: ignore[arg-type]
    )

    assert service.calls == []
    assert result["symbol"] == "FPT"
    assert result["source"] == "KBS"
    assert result["report_type"] == "income-statement"
    assert result["items"] == []
    assert result["data_gaps"] == ["Unsupported financial report period"]


@pytest.mark.asyncio
async def test_load_financial_ratios_uses_kbs_ratio_without_vci_ratio_summary() -> None:
    service = _FakeStockFinancialReportService()

    result = await load_financial_ratios_result(
        {"symbol": "FPT"},
        stock_financial_report_service=service,  # type: ignore[arg-type]
    )

    assert service.calls == [("FPT", StockFinancialReportType.RATIO, "quarter")]
    assert result["source"] == "KBS"
    assert result["report_type"] == "ratio"
