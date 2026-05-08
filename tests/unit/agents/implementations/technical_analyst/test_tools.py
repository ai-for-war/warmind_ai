from __future__ import annotations

from datetime import date

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.agents.implementations.technical_analyst.tools.backtest import (
    run_technical_backtest_result,
)
from app.agents.implementations.technical_analyst.tools.builder import (
    get_technical_analyst_tool_surface,
)
from app.agents.implementations.technical_analyst.tools.compute_indicators import (
    compute_technical_indicators_result,
)
from app.agents.implementations.technical_analyst.tools.price_history import (
    load_price_history_result,
)
from app.domain.schemas.backtest import (
    BacktestPerformanceMetrics,
    BacktestRunResponse,
    BacktestSummaryMetrics,
)
from app.domain.schemas.stock_price import (
    StockPriceHistoryItem,
    StockPriceHistoryResponse,
)


class _FakeStockPriceService:
    def __init__(self, items: list[StockPriceHistoryItem]) -> None:
        self.items = items
        self.calls: list[tuple[str, object]] = []

    async def get_history(self, symbol: str, query) -> StockPriceHistoryResponse:
        self.calls.append((symbol, query))
        return StockPriceHistoryResponse(
            symbol=symbol.upper(),
            source=query.source,
            interval=query.interval,
            cache_hit=False,
            items=self.items,
        )


class _FakeBacktestService:
    def __init__(self) -> None:
        self.requests: list[object] = []

    async def run_backtest(self, request) -> BacktestRunResponse:
        self.requests.append(request)
        return BacktestRunResponse(
            summary_metrics=BacktestSummaryMetrics(
                symbol=request.symbol,
                template_id=request.template_id,
                timeframe=request.timeframe,
                date_from=request.date_from,
                date_to=request.date_to,
                initial_capital=request.initial_capital,
                ending_equity=112_000_000,
                total_trades=3,
            ),
            performance_metrics=BacktestPerformanceMetrics(
                total_return_pct=12.0,
                annualized_return_pct=10.5,
                max_drawdown_pct=-6.2,
                win_rate_pct=66.7,
                profit_factor=1.8,
                avg_win_pct=7.5,
                avg_loss_pct=-3.2,
                expectancy=2.1,
            ),
            trade_log=[],
            equity_curve=[],
        )


def _bars(count: int) -> list[StockPriceHistoryItem]:
    bars: list[StockPriceHistoryItem] = []
    price = 100.0
    for index in range(count):
        price += 0.25
        bars.append(
            StockPriceHistoryItem(
                time=f"2025-01-{(index % 28) + 1:02d}",
                open=price - 0.4,
                high=price + 1.0,
                low=price - 1.0,
                close=price,
                volume=1_000 + index,
            )
        )
    return bars


def test_technical_analyst_tool_surface_exposes_only_dedicated_tools() -> None:
    surface = get_technical_analyst_tool_surface()

    assert [tool.name for tool in surface.tools] == [
        "compute_technical_indicators",
        "load_price_history",
        "run_backtest",
    ]


def test_technical_analyst_tool_schemas_are_strict_provider_compatible() -> None:
    missing_required: list[tuple[str, list[str]]] = []

    def check_object_schema(node: object, path: str) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict) and properties:
                required = set(node.get("required") or [])
                missing = sorted(set(properties) - required)
                if missing:
                    missing_required.append((path, missing))
            for key, value in node.items():
                check_object_schema(value, f"{path}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                check_object_schema(value, f"{path}/{index}")

    for tool in get_technical_analyst_tool_surface().tools:
        check_object_schema(convert_to_openai_tool(tool), tool.name)

    assert missing_required == []


@pytest.mark.asyncio
async def test_compute_indicators_self_loads_history_and_returns_snapshot() -> None:
    stock_price_service = _FakeStockPriceService(_bars(260))

    snapshot = await compute_technical_indicators_result(
        {"symbol": "fpt", "length": 260, "indicator_set": "core"},
        stock_price_service=stock_price_service,  # type: ignore[arg-type]
    )

    assert stock_price_service.calls
    symbol, query = stock_price_service.calls[0]
    assert symbol == "FPT"
    assert query.length == 260
    assert query.interval == "1D"
    assert snapshot.symbol == "FPT"
    assert snapshot.bars_loaded == 260
    assert snapshot.indicator_set == "core"
    assert {reading.name for reading in snapshot.trend} >= {
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_20",
        "adx_14",
    }
    assert {reading.name for reading in snapshot.momentum} >= {
        "rsi_14",
        "macd_12_26_9",
    }
    assert {reading.name for reading in snapshot.volatility} >= {
        "bollinger_upper_20",
        "atr_14",
    }
    assert {reading.name for reading in snapshot.volume} >= {
        "obv",
        "volume_avg_20",
    }
    assert snapshot.support_levels
    assert snapshot.resistance_levels
    assert snapshot.unavailable_indicators == []


@pytest.mark.asyncio
async def test_compute_indicators_reports_unavailable_values_for_short_history() -> None:
    stock_price_service = _FakeStockPriceService(_bars(5))

    snapshot = await compute_technical_indicators_result(
        {"symbol": "fpt", "length": 5, "indicator_set": "core"},
        stock_price_service=stock_price_service,  # type: ignore[arg-type]
    )

    assert snapshot.bars_loaded == 5
    assert "sma_20" in snapshot.unavailable_indicators
    assert "sma_200" in snapshot.unavailable_indicators
    assert "rsi_14" in snapshot.unavailable_indicators
    assert "volume_avg_20" in snapshot.unavailable_indicators


@pytest.mark.asyncio
async def test_compute_indicators_honors_custom_config() -> None:
    stock_price_service = _FakeStockPriceService(_bars(80))

    snapshot = await compute_technical_indicators_result(
        {
            "symbol": "fpt",
            "start": "2025-01-01",
            "end": "2025-12-31",
            "indicator_set": "custom",
            "config": {
                "sma_windows": [10],
                "include_support_resistance": True,
            },
        },
        stock_price_service=stock_price_service,  # type: ignore[arg-type]
    )

    _, query = stock_price_service.calls[0]
    assert query.start == "2025-01-01"
    assert query.end == "2025-12-31"
    assert snapshot.indicator_set == "custom"
    assert [reading.name for reading in snapshot.trend] == ["sma_10"]
    assert snapshot.support_levels
    assert snapshot.resistance_levels


@pytest.mark.asyncio
async def test_load_price_history_returns_raw_ohlcv_and_is_not_required_before_compute() -> None:
    stock_price_service = _FakeStockPriceService(_bars(30))

    snapshot = await compute_technical_indicators_result(
        {"symbol": "fpt", "length": 30, "indicator_set": "trend"},
        stock_price_service=stock_price_service,  # type: ignore[arg-type]
    )
    raw = await load_price_history_result(
        {"symbol": "fpt", "length": 30},
        stock_price_service=stock_price_service,  # type: ignore[arg-type]
    )

    assert snapshot.symbol == "FPT"
    assert raw["symbol"] == "FPT"
    assert raw["interval"] == "1D"
    assert raw["bars_loaded"] == 30
    assert set(raw["items"][0]) == {"time", "open", "high", "low", "close", "volume"}
    assert len(stock_price_service.calls) == 2


@pytest.mark.asyncio
async def test_run_backtest_routes_supported_template_to_internal_service() -> None:
    backtest_service = _FakeBacktestService()

    result = await run_technical_backtest_result(
        {
            "symbol": "fpt",
            "date_from": "2025-01-01",
            "date_to": "2025-12-31",
            "template_id": "sma_crossover",
            "template_params": {"fast_window": 20, "slow_window": 50},
        },
        backtest_service=backtest_service,  # type: ignore[arg-type]
    )

    request = backtest_service.requests[0]
    assert request.symbol == "FPT"
    assert request.template_id == "sma_crossover"
    assert request.timeframe == "1D"
    assert request.date_from == date(2025, 1, 1)
    assert result["summary"]["template_id"] == "sma_crossover"
    assert result["summary"]["total_return_pct"] == 12.0
    assert result["trade_log_count"] == 0


@pytest.mark.asyncio
async def test_run_backtest_rejects_unsupported_scope_before_service_call() -> None:
    backtest_service = _FakeBacktestService()

    with pytest.raises(ValueError, match="sma_crossover requires template_params"):
        await run_technical_backtest_result(
            {
                "symbol": "fpt",
                "date_from": "2025-01-01",
                "date_to": "2025-12-31",
                "template_id": "sma_crossover",
            },
            backtest_service=backtest_service,  # type: ignore[arg-type]
        )

    assert backtest_service.requests == []
