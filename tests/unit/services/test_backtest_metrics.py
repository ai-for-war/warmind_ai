from __future__ import annotations

from datetime import date

import pytest

from app.domain.schemas.backtest import (
    BacktestEquityCurvePoint,
    BacktestPerformanceMetrics,
    BacktestRunRequest,
    BacktestTradeLogEntry,
)
from app.services.backtest.engine import BacktestEngineResult
from app.services.backtest.metrics import BacktestMetricsBuilder


def _request(**overrides: object) -> BacktestRunRequest:
    payload: dict[str, object] = {
        "symbol": "FPT",
        "date_from": date(2024, 1, 1),
        "date_to": date(2024, 12, 31),
        "initial_capital": 1000,
    }
    payload.update(overrides)
    return BacktestRunRequest(**payload)


def _trade(
    *,
    entry_time: str = "2024-01-02",
    entry_price: float = 10.0,
    exit_time: str = "2024-01-03",
    exit_price: float = 11.0,
    shares: int = 100,
    invested_capital: float = 1000.0,
    pnl: float,
    pnl_pct: float,
    exit_reason: str = "exit",
) -> BacktestTradeLogEntry:
    return BacktestTradeLogEntry(
        entry_time=entry_time,
        entry_price=entry_price,
        exit_time=exit_time,
        exit_price=exit_price,
        shares=shares,
        invested_capital=invested_capital,
        pnl=pnl,
        pnl_pct=pnl_pct,
        exit_reason=exit_reason,
    )


def _equity_point(
    time: str,
    *,
    cash: float,
    market_value: float,
    equity: float,
    drawdown_pct: float,
    position_size: int,
) -> BacktestEquityCurvePoint:
    return BacktestEquityCurvePoint(
        time=time,
        cash=cash,
        market_value=market_value,
        equity=equity,
        drawdown_pct=drawdown_pct,
        position_size=position_size,
    )


def test_metrics_builder_returns_zeroed_metrics_when_no_execution_outputs_exist() -> None:
    builder = BacktestMetricsBuilder()

    response = builder.build_response(
        _request(),
        BacktestEngineResult(trade_log=[], equity_curve=[]),
    )

    assert response.summary_metrics.ending_equity == 1000
    assert response.summary_metrics.total_trades == 0
    assert response.performance_metrics == BacktestPerformanceMetrics(
        total_return_pct=0.0,
        annualized_return_pct=0.0,
        max_drawdown_pct=0.0,
        win_rate_pct=0.0,
        profit_factor=0.0,
        avg_win_pct=0.0,
        avg_loss_pct=0.0,
        expectancy=0.0,
    )


def test_metrics_builder_aggregates_mixed_trade_statistics_exactly() -> None:
    builder = BacktestMetricsBuilder()
    request = _request()
    result = BacktestEngineResult(
        trade_log=[
            _trade(pnl=100.0, pnl_pct=10.0, exit_reason="win"),
            _trade(pnl=-50.0, pnl_pct=-5.0, exit_reason="loss_1"),
            _trade(pnl=-150.0, pnl_pct=-15.0, exit_reason="loss_2"),
        ],
        equity_curve=[
            _equity_point(
                "2024-01-02",
                cash=0.0,
                market_value=1100.0,
                equity=1100.0,
                drawdown_pct=0.0,
                position_size=100,
            ),
            _equity_point(
                "2024-06-01",
                cash=0.0,
                market_value=880.0,
                equity=880.0,
                drawdown_pct=20.0,
                position_size=100,
            ),
            _equity_point(
                "2024-12-31",
                cash=900.0,
                market_value=0.0,
                equity=900.0,
                drawdown_pct=18.181818181818183,
                position_size=0,
            ),
        ],
    )

    response = builder.build_response(request, result)

    assert response.summary_metrics.ending_equity == 900
    assert response.performance_metrics.total_return_pct == -10
    assert response.performance_metrics.annualized_return_pct == pytest.approx(-10.0)
    assert response.performance_metrics.max_drawdown_pct == 20
    assert response.performance_metrics.win_rate_pct == pytest.approx(100 / 3)
    assert response.performance_metrics.profit_factor == 0.5
    assert response.performance_metrics.avg_win_pct == 10
    assert response.performance_metrics.avg_loss_pct == -10
    assert response.performance_metrics.expectancy == pytest.approx(-10 / 3)


def test_metrics_builder_profit_factor_and_loss_metrics_handle_all_wins() -> None:
    builder = BacktestMetricsBuilder()
    result = BacktestEngineResult(
        trade_log=[
            _trade(pnl=100.0, pnl_pct=10.0, exit_reason="win_1"),
            _trade(pnl=50.0, pnl_pct=5.0, exit_reason="win_2"),
        ],
        equity_curve=[
            _equity_point(
                "2024-12-31",
                cash=1150.0,
                market_value=0.0,
                equity=1150.0,
                drawdown_pct=0.0,
                position_size=0,
            )
        ],
    )

    response = builder.build_response(_request(), result)

    assert response.performance_metrics.profit_factor == 150
    assert response.performance_metrics.avg_win_pct == 7.5
    assert response.performance_metrics.avg_loss_pct == 0
    assert response.performance_metrics.expectancy == 7.5

