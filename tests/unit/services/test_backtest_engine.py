from __future__ import annotations

from datetime import date

import pytest

from app.domain.schemas.backtest import BacktestBar, BacktestRunRequest
from app.services.backtest.engine import BacktestEngine
from app.services.backtest.metrics import BacktestMetricsBuilder
from app.services.backtest.templates import BacktestSignal


def _build_request(**overrides: object) -> BacktestRunRequest:
    payload: dict[str, object] = {
        "symbol": "FPT",
        "date_from": date(2024, 1, 1),
        "date_to": date(2024, 12, 31),
        "initial_capital": 1000,
    }
    payload.update(overrides)
    return BacktestRunRequest(**payload)


def _bar(
    time: str,
    *,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float = 1000,
) -> BacktestBar:
    return BacktestBar(
        time=time,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_engine_uses_next_open_fills_and_ignores_repeated_buy_signals() -> None:
    engine = BacktestEngine()
    request = _build_request()
    bars = [
        _bar("2024-01-01", open=10, high=10, low=10, close=10),
        _bar("2024-01-02", open=11, high=11, low=11, close=11),
        _bar("2024-01-03", open=12, high=12, low=12, close=12),
        _bar("2024-01-04", open=8, high=8, low=8, close=8),
    ]
    signals = [
        BacktestSignal(
            bar_index=0,
            time="2024-01-01",
            action="buy",
            reason="initial_entry",
        ),
        BacktestSignal(
            bar_index=1,
            time="2024-01-02",
            action="buy",
            reason="repeat_entry",
        ),
        BacktestSignal(
            bar_index=2,
            time="2024-01-03",
            action="sell",
            reason="trend_exit",
        ),
    ]

    result = engine.run(request, bars, signals)

    assert len(result.trade_log) == 1
    trade = result.trade_log[0]
    assert trade.entry_time == "2024-01-02"
    assert trade.entry_price == 11
    assert trade.exit_time == "2024-01-04"
    assert trade.exit_price == 8
    assert trade.shares == 90
    assert trade.exit_reason == "trend_exit"

    assert [point.position_size for point in result.equity_curve] == [0, 90, 90, 0]
    assert result.equity_curve[1].cash == 10
    assert result.equity_curve[3].equity == 730


def test_engine_force_closes_open_position_at_final_close() -> None:
    engine = BacktestEngine()
    request = _build_request()
    bars = [
        _bar("2024-01-01", open=10, high=10, low=10, close=10),
        _bar("2024-01-02", open=10, high=11, low=10, close=11),
        _bar("2024-01-03", open=11, high=12, low=11, close=12),
    ]
    signals = [
        BacktestSignal(
            bar_index=0,
            time="2024-01-01",
            action="buy",
            reason="buy_and_hold_entry",
        )
    ]

    result = engine.run(request, bars, signals)

    assert len(result.trade_log) == 1
    trade = result.trade_log[0]
    assert trade.entry_time == "2024-01-02"
    assert trade.entry_price == 10
    assert trade.exit_time == "2024-01-03"
    assert trade.exit_price == 12
    assert trade.exit_reason == "end_of_window"
    assert trade.pnl == 200
    assert trade.pnl_pct == 20

    final_point = result.equity_curve[-1]
    assert final_point.cash == 1200
    assert final_point.market_value == 0
    assert final_point.equity == 1200
    assert final_point.position_size == 0


def test_engine_returns_empty_outputs_without_bars() -> None:
    engine = BacktestEngine()

    result = engine.run(_build_request(), [], [])

    assert result.trade_log == []
    assert result.equity_curve == []


def test_engine_ignores_sell_without_position_and_drops_last_bar_buy_signal() -> None:
    engine = BacktestEngine()
    request = _build_request()
    bars = [
        _bar("2024-01-01", open=10, high=10, low=10, close=10),
        _bar("2024-01-02", open=11, high=11, low=11, close=11),
    ]
    signals = [
        BacktestSignal(
            bar_index=0,
            time="2024-01-01",
            action="sell",
            reason="ignored_exit_without_position",
        ),
        BacktestSignal(
            bar_index=1,
            time="2024-01-02",
            action="buy",
            reason="cannot_fill_without_next_bar",
        ),
    ]

    result = engine.run(request, bars, signals)

    assert result.trade_log == []
    assert [point.position_size for point in result.equity_curve] == [0, 0]
    assert [point.equity for point in result.equity_curve] == [1000, 1000]


def test_engine_all_in_uses_floor_share_count_and_preserves_residual_cash() -> None:
    engine = BacktestEngine()
    request = _build_request()
    bars = [
        _bar("2024-01-01", open=5, high=5, low=5, close=5),
        _bar("2024-01-02", open=6, high=7, low=6, close=7),
        _bar("2024-01-03", open=8, high=8, low=8, close=8),
    ]
    signals = [
        BacktestSignal(
            bar_index=0,
            time="2024-01-01",
            action="buy",
            reason="entry",
        )
    ]

    result = engine.run(request, bars, signals)

    assert len(result.trade_log) == 1
    trade = result.trade_log[0]
    assert trade.entry_time == "2024-01-02"
    assert trade.entry_price == 6
    assert trade.shares == 166
    assert trade.invested_capital == 996
    assert trade.exit_time == "2024-01-03"
    assert trade.exit_price == 8
    assert trade.pnl == 332
    assert trade.pnl_pct == pytest.approx((332 / 996) * 100)

    assert result.equity_curve[1].cash == 4
    assert result.equity_curve[1].market_value == 1162
    assert result.equity_curve[1].equity == 1166
    assert result.equity_curve[-1].cash == 1332
    assert result.equity_curve[-1].position_size == 0


def test_engine_reuses_realized_equity_across_multiple_completed_trades() -> None:
    engine = BacktestEngine()
    request = _build_request()
    bars = [
        _bar("2024-01-01", open=10, high=10, low=10, close=10),
        _bar("2024-01-02", open=10, high=11, low=10, close=11),
        _bar("2024-01-03", open=11, high=12, low=11, close=12),
        _bar("2024-01-04", open=13, high=13, low=13, close=13),
        _bar("2024-01-05", open=5, high=6, low=5, close=6),
        _bar("2024-01-06", open=6, high=7, low=6, close=7),
        _bar("2024-01-07", open=7, high=7, low=7, close=7),
    ]
    signals = [
        BacktestSignal(
            bar_index=0,
            time="2024-01-01",
            action="buy",
            reason="first_entry",
        ),
        BacktestSignal(
            bar_index=2,
            time="2024-01-03",
            action="sell",
            reason="first_exit",
        ),
        BacktestSignal(
            bar_index=3,
            time="2024-01-04",
            action="buy",
            reason="second_entry",
        ),
        BacktestSignal(
            bar_index=5,
            time="2024-01-06",
            action="sell",
            reason="second_exit",
        ),
    ]

    result = engine.run(request, bars, signals)

    assert len(result.trade_log) == 2

    first_trade, second_trade = result.trade_log
    assert first_trade.entry_price == 10
    assert first_trade.exit_price == 13
    assert first_trade.shares == 100
    assert first_trade.invested_capital == 1000
    assert first_trade.pnl == 300

    assert second_trade.entry_price == 5
    assert second_trade.exit_price == 7
    assert second_trade.shares == 260
    assert second_trade.invested_capital == 1300
    assert second_trade.pnl == 520

    assert result.equity_curve[3].cash == 1300
    assert result.equity_curve[4].cash == 0
    assert result.equity_curve[-1].equity == 1820
    assert result.equity_curve[-1].position_size == 0


def test_engine_equity_curve_tracks_market_value_and_running_drawdown() -> None:
    engine = BacktestEngine()
    request = _build_request()
    bars = [
        _bar("2024-01-01", open=10, high=10, low=10, close=10),
        _bar("2024-01-02", open=10, high=12, low=10, close=12),
        _bar("2024-01-03", open=12, high=12, low=6, close=6),
        _bar("2024-01-04", open=6, high=9, low=6, close=9),
    ]
    signals = [
        BacktestSignal(
            bar_index=0,
            time="2024-01-01",
            action="buy",
            reason="entry",
        )
    ]

    result = engine.run(request, bars, signals)

    assert [point.market_value for point in result.equity_curve[:-1]] == [0, 1200, 600]
    assert [point.equity for point in result.equity_curve[:-1]] == [1000, 1200, 600]
    assert result.equity_curve[1].drawdown_pct == 0
    assert result.equity_curve[2].drawdown_pct == 50
    assert result.equity_curve[-1].cash == 900
    assert result.equity_curve[-1].equity == 900
    assert result.equity_curve[-1].drawdown_pct == 25


def test_metrics_builder_returns_summary_performance_trade_log_and_equity_curve() -> None:
    engine = BacktestEngine()
    metrics_builder = BacktestMetricsBuilder()
    request = _build_request()
    bars = [
        _bar("2024-01-01", open=10, high=10, low=10, close=10),
        _bar("2024-01-02", open=10, high=11, low=10, close=11),
        _bar("2024-01-03", open=11, high=12, low=11, close=12),
    ]
    signals = [
        BacktestSignal(
            bar_index=0,
            time="2024-01-01",
            action="buy",
            reason="buy_and_hold_entry",
        )
    ]

    execution_result = engine.run(request, bars, signals)
    response = metrics_builder.build_response(request, execution_result)

    assert response.summary_metrics.symbol == "FPT"
    assert response.summary_metrics.ending_equity == 1200
    assert response.summary_metrics.total_trades == 1
    assert response.performance_metrics.total_return_pct == 20
    assert response.performance_metrics.annualized_return_pct == pytest.approx(20.0)
    assert response.performance_metrics.max_drawdown_pct == 0
    assert response.performance_metrics.win_rate_pct == 100
    assert response.performance_metrics.profit_factor == 200
    assert response.performance_metrics.avg_win_pct == 20
    assert response.performance_metrics.avg_loss_pct == 0
    assert response.performance_metrics.expectancy == 20
    assert response.trade_log[0].exit_reason == "end_of_window"
    assert response.equity_curve[-1].position_size == 0
