from __future__ import annotations

from datetime import date

import pytest

from app.domain.schemas.backtest import (
    BacktestBar,
    BacktestRunRequest,
    BuyAndHoldTemplateParams,
    IchimokuCloudTemplateParams,
    SmaCrossoverTemplateParams,
)
from app.domain.schemas.stock_price import StockPriceHistoryResponse
from app.services.backtest.data_service import BacktestBarWindow, BacktestDataService
from app.services.backtest.engine import BacktestEngine
from app.services.backtest.metrics import BacktestMetricsBuilder
from app.services.backtest.templates import BacktestTemplateRegistry, IchimokuCloudTemplate


class _FakeStockPriceService:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items
        self.calls: list[tuple[str, object]] = []

    async def get_history(self, symbol: str, query) -> StockPriceHistoryResponse:
        self.calls.append((symbol, query))
        return StockPriceHistoryResponse(
            symbol=symbol,
            source=query.source,
            cache_hit=False,
            interval="1D",
            items=self.items,
        )


def _build_request(**overrides: object) -> BacktestRunRequest:
    payload: dict[str, object] = {
        "symbol": "FPT",
        "date_from": date(2024, 1, 1),
        "date_to": date(2024, 1, 31),
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


@pytest.mark.asyncio
async def test_backtest_data_service_loads_ordered_daily_bars_from_stock_history() -> None:
    stock_price_service = _FakeStockPriceService(
        [
            {
                "time": "2023-12-31",
                "open": 9.5,
                "high": 10.0,
                "low": 9.0,
                "close": 9.8,
                "volume": 800,
            },
            {
                "time": "2024-01-03",
                "open": 11.0,
                "high": 12.0,
                "low": 10.0,
                "close": 11.5,
                "volume": 1000,
            },
            {
                "time": "2024-01-02",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 900,
            },
            {
                "time": "2024-02-01",
                "open": 12.0,
                "high": 12.5,
                "low": 11.8,
                "close": 12.3,
                "volume": 1100,
            },
        ]
    )
    service = BacktestDataService(stock_price_service)  # type: ignore[arg-type]

    window = await service.load_bars(_build_request(), minimum_history_bars=2)

    assert isinstance(window, BacktestBarWindow)
    assert [bar.time for bar in window.warmup_bars] == ["2023-12-31"]
    assert [bar.time for bar in window.tradable_bars] == ["2024-01-02", "2024-01-03"]
    assert [bar.time for bar in window.all_bars] == [
        "2023-12-31",
        "2024-01-02",
        "2024-01-03",
    ]
    symbol, query = stock_price_service.calls[0]
    assert symbol == "FPT"
    assert query.start == "2023-12-30"
    assert query.end == "2024-01-31"
    assert query.interval == "1D"
    assert query.source == "KBS"


@pytest.mark.asyncio
async def test_backtest_data_service_rejects_insufficient_history() -> None:
    stock_price_service = _FakeStockPriceService(
        [
            {
                "time": "2024-01-02",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 900,
            }
        ]
    )
    service = BacktestDataService(stock_price_service)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="Not enough pre-window daily history to satisfy the selected backtest template",
    ):
        await service.load_bars(_build_request(), minimum_history_bars=2)


@pytest.mark.asyncio
async def test_backtest_data_service_rejects_empty_history() -> None:
    service = BacktestDataService(_FakeStockPriceService([]))  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="No tradable daily history is available in the requested backtest window",
    ):
        await service.load_bars(_build_request(), minimum_history_bars=1)


@pytest.mark.asyncio
async def test_backtest_data_service_rejects_invalid_history_bar_payload() -> None:
    stock_price_service = _FakeStockPriceService(
        [
            {
                "time": "2024-01-02",
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 900,
            }
        ]
    )
    service = BacktestDataService(stock_price_service)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="Stock price history contains invalid backtest bars",
    ):
        await service.load_bars(_build_request(), minimum_history_bars=1)


@pytest.mark.asyncio
async def test_backtest_data_service_rejects_non_positive_minimum_history_bars() -> None:
    service = BacktestDataService(_FakeStockPriceService([]))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="minimum_history_bars must be greater than zero"):
        await service.load_bars(_build_request(), minimum_history_bars=0)


@pytest.mark.asyncio
async def test_backtest_data_service_rejects_insufficient_tradable_history() -> None:
    stock_price_service = _FakeStockPriceService(
        [
            {
                "time": "2023-12-30",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 900,
            },
            {
                "time": "2024-01-02",
                "open": 10.5,
                "high": 11.5,
                "low": 10.0,
                "close": 11.0,
                "volume": 950,
            },
        ]
    )
    service = BacktestDataService(stock_price_service)  # type: ignore[arg-type]

    with pytest.raises(
        ValueError,
        match="Not enough tradable daily history to execute the selected backtest template",
    ):
        await service.load_bars(
            _build_request(),
            minimum_history_bars=1,
            minimum_tradable_bars=2,
        )


def test_buy_and_hold_template_generates_one_initial_buy_signal() -> None:
    registry = BacktestTemplateRegistry()
    bars = [
        _bar("2024-01-02", open=10, high=11, low=9.5, close=10.5),
        _bar("2024-01-03", open=10.5, high=11.5, low=10, close=11),
    ]

    signals = registry.generate_signals(
        "buy_and_hold",
        bars,
        BuyAndHoldTemplateParams(),
    )

    assert signals == [
        registry.get_template("buy_and_hold").generate_signals(
            bars,
            BuyAndHoldTemplateParams(),
        )[0]
    ]
    assert signals[0].action == "buy"
    assert signals[0].bar_index == 0
    assert signals[0].reason == "buy_and_hold_entry"


def test_buy_and_hold_template_requires_one_bar_and_returns_no_signal_without_bars() -> None:
    registry = BacktestTemplateRegistry()

    assert registry.required_history_bars("buy_and_hold", BuyAndHoldTemplateParams()) == 1
    assert (
        registry.generate_signals("buy_and_hold", [], BuyAndHoldTemplateParams()) == []
    )


def test_sma_crossover_template_generates_buy_and_sell_cross_signals() -> None:
    registry = BacktestTemplateRegistry()
    params = SmaCrossoverTemplateParams(fast_window=2, slow_window=3)
    bars = [
        _bar("2024-01-01", open=10, high=10, low=10, close=10),
        _bar("2024-01-02", open=9, high=9, low=9, close=9),
        _bar("2024-01-03", open=8, high=8, low=8, close=8),
        _bar("2024-01-04", open=12, high=12, low=12, close=12),
        _bar("2024-01-05", open=14, high=14, low=14, close=14),
        _bar("2024-01-06", open=7, high=7, low=7, close=7),
    ]

    signals = registry.generate_signals("sma_crossover", bars, params)

    assert [(signal.action, signal.bar_index) for signal in signals] == [
        ("buy", 3),
        ("sell", 5),
    ]
    assert signals[0].reason == "sma_fast_crosses_above_sma_slow"
    assert signals[1].reason == "sma_fast_crosses_below_sma_slow"


def test_sma_crossover_returns_no_signal_when_history_is_shorter_than_required() -> None:
    registry = BacktestTemplateRegistry()
    params = SmaCrossoverTemplateParams(fast_window=2, slow_window=3)
    bars = [
        _bar("2024-01-01", open=10, high=10, low=10, close=10),
        _bar("2024-01-02", open=9, high=9, low=9, close=9),
        _bar("2024-01-03", open=8, high=8, low=8, close=8),
    ]

    assert registry.generate_signals("sma_crossover", bars, params) == []


def test_sma_crossover_required_history_uses_slow_window_plus_one() -> None:
    registry = BacktestTemplateRegistry()

    required = registry.required_history_bars(
        "sma_crossover",
        SmaCrossoverTemplateParams(fast_window=20, slow_window=50),
    )

    assert required == 51


def test_template_registry_reports_supported_template_ids_in_stable_order() -> None:
    registry = BacktestTemplateRegistry()

    assert registry.supported_template_ids() == (
        "buy_and_hold",
        "sma_crossover",
        "ichimoku_cloud",
    )


def test_ichimoku_cloud_generates_bullish_entry_from_aligned_cloud_and_warmup() -> None:
    registry = BacktestTemplateRegistry()
    params = IchimokuCloudTemplateParams(
        tenkan_window=2,
        kijun_window=3,
        senkou_b_window=4,
        displacement=1,
        warmup_bars=5,
    )
    bars = [
        _bar("2024-01-01", open=9, high=10, low=8, close=9),
        _bar("2024-01-02", open=8, high=9, low=4, close=6),
        _bar("2024-01-03", open=7, high=8, low=6, close=7),
        _bar("2024-01-04", open=8, high=9, low=6, close=8),
        _bar("2024-01-05", open=9, high=10, low=7, close=7),
        _bar("2024-01-06", open=12, high=14, low=10, close=13),
    ]

    signals = registry.generate_signals(
        "ichimoku_cloud",
        bars,
        params,
        tradable_start_index=5,
    )

    assert [(signal.action, signal.bar_index, signal.reason) for signal in signals] == [
        (
            "buy",
            0,
            "ichimoku_price_above_bullish_cloud_with_bullish_tk_cross",
        )
    ]


def test_ichimoku_cloud_generates_sell_on_aligned_cloud_breakdown() -> None:
    registry = BacktestTemplateRegistry()
    params = IchimokuCloudTemplateParams(
        tenkan_window=2,
        kijun_window=3,
        senkou_b_window=4,
        displacement=1,
        warmup_bars=5,
    )
    bars = [
        _bar("2024-01-01", open=9, high=10, low=8, close=9),
        _bar("2024-01-02", open=8, high=9, low=4, close=6),
        _bar("2024-01-03", open=7, high=8, low=6, close=7),
        _bar("2024-01-04", open=8, high=9, low=6, close=8),
        _bar("2024-01-05", open=9, high=10, low=7, close=7),
        _bar("2024-01-06", open=6, high=7, low=5, close=6),
    ]

    signals = registry.generate_signals(
        "ichimoku_cloud",
        bars,
        params,
        tradable_start_index=5,
    )

    assert [(signal.action, signal.bar_index, signal.reason) for signal in signals] == [
        ("sell", 0, "ichimoku_close_below_aligned_cloud")
    ]


def test_ichimoku_cloud_warning_state_does_not_create_extra_trade() -> None:
    template = IchimokuCloudTemplate()
    params = IchimokuCloudTemplateParams(
        tenkan_window=2,
        kijun_window=3,
        senkou_b_window=4,
        displacement=1,
        warmup_bars=5,
    )
    bars = [
        _bar("2024-01-01", open=9, high=10, low=8, close=9),
        _bar("2024-01-02", open=8, high=9, low=4, close=6),
        _bar("2024-01-03", open=7, high=8, low=6, close=7),
        _bar("2024-01-04", open=8, high=9, low=6, close=8),
        _bar("2024-01-05", open=9, high=10, low=7, close=7),
        _bar("2024-01-06", open=12, high=14, low=10, close=13),
        _bar("2024-01-07", open=10.5, high=14, low=9, close=10.2),
    ]

    signals = template.generate_signals(
        bars,
        params,
        tradable_start_index=5,
    )
    warnings = template.evaluate_warning_states(
        bars,
        params,
        tradable_start_index=5,
    )

    assert [(signal.action, signal.bar_index) for signal in signals] == [("buy", 0)]
    assert [(warning.bar_index, warning.reasons) for warning in warnings] == [
        (
            1,
            (
                "close_below_kijun",
                "chikou_confirmation_lost",
            ),
        )
    ]


def test_ichimoku_cloud_golden_dataset_produces_expected_trade_flow() -> None:
    registry = BacktestTemplateRegistry()
    engine = BacktestEngine()
    metrics_builder = BacktestMetricsBuilder()
    params = IchimokuCloudTemplateParams(
        tenkan_window=2,
        kijun_window=3,
        senkou_b_window=4,
        displacement=1,
        warmup_bars=5,
    )
    all_bars = [
        _bar("2024-01-01", open=9, high=10, low=8, close=9),
        _bar("2024-01-02", open=8, high=9, low=4, close=6),
        _bar("2024-01-03", open=7, high=8, low=6, close=7),
        _bar("2024-01-04", open=8, high=9, low=6, close=8),
        _bar("2024-01-05", open=9, high=10, low=7, close=7),
        _bar("2024-01-06", open=12, high=14, low=10, close=13),
        _bar("2024-01-07", open=10.5, high=14, low=9, close=10.2),
        _bar("2024-01-08", open=9.8, high=10, low=8, close=8.5),
        _bar("2024-01-09", open=8.2, high=8.4, low=7.5, close=7.8),
    ]
    tradable_start_index = 5
    tradable_bars = all_bars[tradable_start_index:]
    request = BacktestRunRequest(
        symbol="FPT",
        date_from=date(2024, 1, 6),
        date_to=date(2024, 1, 9),
        template_id="ichimoku_cloud",
        template_params=params,
    )

    signals = registry.generate_signals(
        "ichimoku_cloud",
        all_bars,
        params,
        tradable_start_index=tradable_start_index,
    )
    warnings = registry.get_template("ichimoku_cloud").evaluate_warning_states(  # type: ignore[attr-defined]
        all_bars,
        params,
        tradable_start_index=tradable_start_index,
    )
    execution_result = engine.run(request, tradable_bars, signals)
    response = metrics_builder.build_response(request, execution_result)

    assert [(signal.action, signal.bar_index, signal.time, signal.reason) for signal in signals] == [
        (
            "buy",
            0,
            "2024-01-06",
            "ichimoku_price_above_bullish_cloud_with_bullish_tk_cross",
        ),
        (
            "sell",
            2,
            "2024-01-08",
            "ichimoku_close_below_aligned_cloud",
        ),
        (
            "sell",
            3,
            "2024-01-09",
            "ichimoku_close_below_aligned_cloud",
        ),
    ]
    assert [(warning.bar_index, warning.time, warning.reasons) for warning in warnings] == [
        (
            1,
            "2024-01-07",
            (
                "close_below_kijun",
                "chikou_confirmation_lost",
            ),
        )
    ]
    assert len(execution_result.trade_log) == 1
    trade = execution_result.trade_log[0]
    assert trade.entry_time == "2024-01-07"
    assert trade.entry_price == pytest.approx(10.5)
    assert trade.exit_time == "2024-01-09"
    assert trade.exit_price == pytest.approx(8.2)
    assert trade.exit_reason == "ichimoku_close_below_aligned_cloud"
    assert trade.pnl == pytest.approx(-21_904_760.7)
    assert trade.pnl_pct == pytest.approx(-21.9047619)
    assert response.summary_metrics.total_trades == 1
    assert response.summary_metrics.ending_equity == pytest.approx(78_095_239.3)
    assert response.equity_curve[-1].time == "2024-01-09"
    assert response.equity_curve[-1].position_size == 0


def test_ichimoku_cloud_golden_dataset_covers_bearish_tk_cross_exit_flow() -> None:
    registry = BacktestTemplateRegistry()
    engine = BacktestEngine()
    metrics_builder = BacktestMetricsBuilder()
    params = IchimokuCloudTemplateParams(
        tenkan_window=2,
        kijun_window=3,
        senkou_b_window=4,
        displacement=1,
        warmup_bars=5,
    )
    all_bars = [
        _bar("2024-01-01", open=9, high=10, low=8, close=9),
        _bar("2024-01-02", open=8, high=9, low=4, close=6),
        _bar("2024-01-03", open=7, high=8, low=6, close=7),
        _bar("2024-01-04", open=8, high=9, low=6, close=8),
        _bar("2024-01-05", open=9, high=10, low=7, close=7),
        _bar("2024-01-06", open=12, high=14, low=10, close=13),
        _bar("2024-01-07", open=12, high=13, low=11, close=12.5),
        _bar("2024-01-08", open=11, high=12, low=9, close=10.8),
        _bar("2024-01-09", open=11, high=12, low=10, close=11.2),
    ]
    tradable_start_index = 5
    tradable_bars = all_bars[tradable_start_index:]
    request = BacktestRunRequest(
        symbol="FPT",
        date_from=date(2024, 1, 6),
        date_to=date(2024, 1, 9),
        template_id="ichimoku_cloud",
        template_params=params,
    )

    signals = registry.generate_signals(
        "ichimoku_cloud",
        all_bars,
        params,
        tradable_start_index=tradable_start_index,
    )
    warnings = registry.get_template("ichimoku_cloud").evaluate_warning_states(  # type: ignore[attr-defined]
        all_bars,
        params,
        tradable_start_index=tradable_start_index,
    )
    execution_result = engine.run(request, tradable_bars, signals)
    response = metrics_builder.build_response(request, execution_result)

    assert [(signal.action, signal.bar_index, signal.time, signal.reason) for signal in signals] == [
        (
            "buy",
            0,
            "2024-01-06",
            "ichimoku_price_above_bullish_cloud_with_bullish_tk_cross",
        ),
        (
            "sell",
            2,
            "2024-01-08",
            "ichimoku_bearish_tk_cross_with_kijun_loss",
        ),
    ]
    assert [(warning.bar_index, warning.time, warning.reasons) for warning in warnings] == [
        (
            1,
            "2024-01-07",
            ("chikou_confirmation_lost",),
        ),
        (
            3,
            "2024-01-09",
            ("chikou_confirmation_lost",),
        ),
    ]
    assert len(execution_result.trade_log) == 1
    trade = execution_result.trade_log[0]
    assert trade.entry_time == "2024-01-07"
    assert trade.entry_price == pytest.approx(12.0)
    assert trade.exit_time == "2024-01-09"
    assert trade.exit_price == pytest.approx(11.0)
    assert trade.exit_reason == "ichimoku_bearish_tk_cross_with_kijun_loss"
    assert trade.pnl == pytest.approx(-8_333_333.0)
    assert trade.pnl_pct == pytest.approx(-8.333333333333332)
    assert response.summary_metrics.total_trades == 1
    assert response.summary_metrics.ending_equity == pytest.approx(91_666_667.0)
    assert response.equity_curve[-1].time == "2024-01-09"
    assert response.equity_curve[-1].position_size == 0
