from __future__ import annotations

from datetime import date

import pytest

from app.domain.schemas.backtest import (
    BacktestBar,
    BacktestRunRequest,
    BuyAndHoldTemplateParams,
    SmaCrossoverTemplateParams,
)
from app.domain.schemas.stock_price import StockPriceHistoryResponse
from app.services.backtest.data_service import BacktestDataService
from app.services.backtest.templates import BacktestTemplateRegistry


class _FakeStockPriceService:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items
        self.calls: list[tuple[str, object]] = []

    async def get_history(self, symbol: str, query) -> StockPriceHistoryResponse:
        self.calls.append((symbol, query))
        return StockPriceHistoryResponse(
            symbol=symbol,
            source="VCI",
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
        ]
    )
    service = BacktestDataService(stock_price_service)  # type: ignore[arg-type]

    bars = await service.load_bars(_build_request(), minimum_history_bars=2)

    assert [bar.time for bar in bars] == ["2024-01-02", "2024-01-03"]
    symbol, query = stock_price_service.calls[0]
    assert symbol == "FPT"
    assert query.start == "2024-01-01"
    assert query.end == "2024-01-31"
    assert query.interval == "1D"


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
        match="Not enough daily history to execute the selected backtest template",
    ):
        await service.load_bars(_build_request(), minimum_history_bars=2)


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


def test_sma_crossover_required_history_uses_slow_window_plus_one() -> None:
    registry = BacktestTemplateRegistry()

    required = registry.required_history_bars(
        "sma_crossover",
        SmaCrossoverTemplateParams(fast_window=20, slow_window=50),
    )

    assert required == 51
