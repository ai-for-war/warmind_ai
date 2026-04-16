from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.schemas.backtest import (
    BacktestEquityCurvePoint,
    BacktestPerformanceMetrics,
    BacktestRunResponse,
    BacktestSummaryMetrics,
)
from app.domain.schemas.backtest_api import (
    BacktestApiRunAssumptionsResponse,
    BacktestApiRunRequest,
    BacktestApiRunResponse,
    BacktestApiTemplateListResponse,
    BacktestApiTemplateParameterResponse,
    BacktestApiTemplateResponse,
)


def test_backtest_api_run_request_uses_symbol_in_body_and_defaults_initial_capital() -> None:
    request = BacktestApiRunRequest(
        symbol=" fpt ",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 12, 31),
        template_id=" buy_and_hold ",
    )

    assert request.symbol == "FPT"
    assert request.template_id == "buy_and_hold"
    assert request.initial_capital == 100_000_000


def test_backtest_api_run_request_rejects_fixed_engine_fields() -> None:
    with pytest.raises(ValidationError):
        BacktestApiRunRequest(
            symbol="FPT",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            template_id="buy_and_hold",
            timeframe="1D",
        )


def test_backtest_api_run_request_validates_template_params() -> None:
    with pytest.raises(
        ValidationError,
        match="sma_crossover requires template_params with fast_window and slow_window",
    ):
        BacktestApiRunRequest(
            symbol="FPT",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            template_id="sma_crossover",
        )


def test_backtest_api_template_catalog_supports_parameter_metadata() -> None:
    response = BacktestApiTemplateListResponse(
        items=[
            BacktestApiTemplateResponse(
                template_id="sma_crossover",
                display_name="SMA Crossover",
                description="Buy when fast SMA crosses above slow SMA.",
                parameters=[
                    BacktestApiTemplateParameterResponse(
                        name="fast_window",
                        type="integer",
                        required=True,
                        default=20,
                        min=1,
                        description="Fast moving-average lookback window.",
                    )
                ],
            )
        ]
    )

    assert response.items[0].template_id == "sma_crossover"
    assert response.items[0].parameters[0].default == 20


def test_backtest_api_run_response_wraps_result_and_assumptions() -> None:
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
            annualized_return_pct=18.0,
            max_drawdown_pct=5.0,
            win_rate_pct=100.0,
            profit_factor=2.0,
            avg_win_pct=20.0,
            avg_loss_pct=0.0,
            expectancy=20.0,
        ),
        trade_log=[],
        equity_curve=[
            BacktestEquityCurvePoint(
                time="2024-12-31",
                cash=120_000_000,
                market_value=0.0,
                equity=120_000_000,
                drawdown_pct=0.0,
                position_size=0,
            )
        ],
    )
    request = BacktestApiRunRequest(
        symbol="FPT",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 12, 31),
        template_id="buy_and_hold",
    )

    response = BacktestApiRunResponse(
        result=result,
        assumptions=BacktestApiRunAssumptionsResponse.from_run_request(request),
    )

    assert response.result.summary_metrics.symbol == "FPT"
    assert response.assumptions.timeframe == "1D"
    assert response.assumptions.direction == "long_only"
    assert response.assumptions.position_sizing == "all_in"
    assert response.assumptions.execution_model == "next_open"
