"""Backtest tool for the technical analyst runtime."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from app.agents.implementations.technical_analyst.tools.dependencies import (
    get_backtest_service,
)
from app.domain.schemas.backtest import BacktestRunResponse
from app.domain.schemas.technical_analysis import (
    RunTechnicalBacktestInput,
    TechnicalBacktestSummary,
)
from app.services.backtest.service import BacktestService


async def run_technical_backtest_result(
    request: RunTechnicalBacktestInput | dict[str, Any],
    *,
    backtest_service: BacktestService | None = None,
) -> dict[str, Any]:
    """Run one supported internal backtest and return condensed evidence."""
    normalized_request = RunTechnicalBacktestInput.model_validate(request)
    service = backtest_service or get_backtest_service()
    internal_request = normalized_request.to_backtest_run_request()
    response = await service.run_backtest(internal_request)
    summary = _build_backtest_summary(response)
    return {
        "summary": summary.model_dump(mode="json"),
        "summary_metrics": response.summary_metrics.model_dump(mode="json"),
        "performance_metrics": response.performance_metrics.model_dump(mode="json"),
        "trade_log_count": len(response.trade_log),
        "equity_curve_points": len(response.equity_curve),
    }


async def _run_backtest_tool(**kwargs: Any) -> dict[str, Any]:
    return await run_technical_backtest_result(kwargs)


run_backtest = StructuredTool.from_function(
    coroutine=_run_backtest_tool,
    name="run_backtest",
    description=(
        "Run a deterministic supported daily backtest template through the internal "
        "backtest service. The tool rejects unsupported templates, non-daily scope, "
        "and arbitrary model-generated strategy code via schema/service validation."
    ),
    args_schema=RunTechnicalBacktestInput,
)


def _build_backtest_summary(response: BacktestRunResponse) -> TechnicalBacktestSummary:
    return TechnicalBacktestSummary(
        template_id=response.summary_metrics.template_id,
        timeframe=response.summary_metrics.timeframe,
        date_from=response.summary_metrics.date_from,
        date_to=response.summary_metrics.date_to,
        total_return_pct=response.performance_metrics.total_return_pct,
        max_drawdown_pct=response.performance_metrics.max_drawdown_pct,
        win_rate_pct=response.performance_metrics.win_rate_pct,
        total_trades=response.summary_metrics.total_trades,
        profit_factor=response.performance_metrics.profit_factor,
        notes=[
            "Historical deterministic backtest evidence only; not a prediction.",
            "Execution assumptions come from the internal backtest service.",
        ],
    )
