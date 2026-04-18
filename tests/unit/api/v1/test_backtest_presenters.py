from __future__ import annotations

from datetime import date

from app.api.v1.backtests.presenters import build_run_response, build_template_catalog
from app.domain.schemas.backtest import (
    BacktestEquityCurvePoint,
    BacktestPerformanceMetrics,
    BacktestRunResponse,
    BacktestSummaryMetrics,
    BacktestTradeLogEntry,
)
from app.domain.schemas.backtest_api import BacktestApiRunRequest
from app.services.backtest.templates import BacktestTemplateRegistry


class _FakeBacktestService:
    def __init__(self) -> None:
        self.template_registry = BacktestTemplateRegistry()


def test_build_template_catalog_returns_current_v1_templates() -> None:
    response = build_template_catalog(_FakeBacktestService())

    assert [item.template_id for item in response.items] == [
        "buy_and_hold",
        "sma_crossover",
        "ichimoku_cloud",
    ]
    assert response.items[0].parameters == []
    assert [parameter.name for parameter in response.items[1].parameters] == [
        "fast_window",
        "slow_window",
    ]
    assert response.items[1].parameters[0].default == 20
    assert response.items[1].parameters[1].default == 50
    assert [parameter.name for parameter in response.items[2].parameters] == [
        "tenkan_window",
        "kijun_window",
        "senkou_b_window",
        "displacement",
        "warmup_bars",
    ]


def test_build_run_response_wraps_result_and_backend_assumptions() -> None:
    request = BacktestApiRunRequest.model_validate(
        {
            "symbol": "fpt",
            "date_from": "2024-01-01",
            "date_to": "2024-12-31",
            "template_id": "buy_and_hold",
        }
    )
    result = BacktestRunResponse(
        summary_metrics=BacktestSummaryMetrics(
            symbol="FPT",
            template_id="buy_and_hold",
            timeframe="1D",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            initial_capital=100_000_000,
            ending_equity=120_000_000,
            total_trades=1,
        ),
        performance_metrics=BacktestPerformanceMetrics(
            total_return_pct=20.0,
            annualized_return_pct=20.0,
            max_drawdown_pct=5.0,
            win_rate_pct=100.0,
            profit_factor=0.0,
            avg_win_pct=20.0,
            avg_loss_pct=0.0,
            expectancy=20_000_000.0,
        ),
        trade_log=[
            BacktestTradeLogEntry(
                entry_time="2024-01-02",
                entry_price=100.0,
                exit_time="2024-12-31",
                exit_price=120.0,
                shares=1_000,
                invested_capital=100_000.0,
                pnl=20_000.0,
                pnl_pct=20.0,
                exit_reason="end_of_window",
            )
        ],
        equity_curve=[
            BacktestEquityCurvePoint(
                time="2024-01-02",
                cash=0.0,
                market_value=100_000_000.0,
                equity=100_000_000.0,
                drawdown_pct=0.0,
                position_size=1_000,
            )
        ],
    )

    response = build_run_response(request, result)

    assert response.result == result
    assert response.assumptions.timeframe == "1D"
    assert response.assumptions.direction == "long_only"
    assert response.assumptions.position_sizing == "all_in"
    assert response.assumptions.execution_model == "next_open"
    assert response.assumptions.initial_capital == 100_000_000
