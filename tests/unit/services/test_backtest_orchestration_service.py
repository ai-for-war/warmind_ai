from __future__ import annotations

from datetime import date

import pytest

from app.domain.schemas.backtest import (
    BacktestBar,
    BacktestPerformanceMetrics,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestSummaryMetrics,
)
from app.services.backtest.engine import BacktestEngineResult
from app.services.backtest import service as backtest_service_module
from app.services.backtest.service import BacktestService
from app.services.backtest.templates import BacktestSignal


class _FakeDataService:
    def __init__(self, bars: list[BacktestBar], *, error: Exception | None = None) -> None:
        self.bars = bars
        self.error = error
        self.calls: list[tuple[BacktestRunRequest, int]] = []

    async def load_bars(
        self,
        request: BacktestRunRequest,
        *,
        minimum_history_bars: int = 1,
    ) -> list[BacktestBar]:
        self.calls.append((request, minimum_history_bars))
        if self.error is not None:
            raise self.error
        return self.bars


class _FakeTemplateRegistry:
    def __init__(self, *, minimum_history_bars: int, signals: list[BacktestSignal]) -> None:
        self.minimum_history_bars = minimum_history_bars
        self.signals = signals
        self.required_calls: list[tuple[str, object]] = []
        self.signal_calls: list[tuple[str, list[BacktestBar], object]] = []

    def required_history_bars(self, template_id, params) -> int:
        self.required_calls.append((template_id, params))
        return self.minimum_history_bars

    def generate_signals(self, template_id, bars, params) -> list[BacktestSignal]:
        self.signal_calls.append((template_id, bars, params))
        return self.signals


class _FakeEngine:
    def __init__(self, result: BacktestEngineResult) -> None:
        self.result = result
        self.calls: list[tuple[BacktestRunRequest, list[BacktestBar], list[BacktestSignal]]] = []

    def run(
        self,
        request: BacktestRunRequest,
        bars: list[BacktestBar],
        signals: list[BacktestSignal],
    ) -> BacktestEngineResult:
        self.calls.append((request, bars, signals))
        return self.result


class _FakeMetricsBuilder:
    def __init__(self, response: BacktestRunResponse) -> None:
        self.response = response
        self.calls: list[tuple[BacktestRunRequest, BacktestEngineResult]] = []

    def build_response(
        self,
        request: BacktestRunRequest,
        result: BacktestEngineResult,
    ) -> BacktestRunResponse:
        self.calls.append((request, result))
        return self.response


def _request(**overrides: object) -> BacktestRunRequest:
    payload: dict[str, object] = {
        "symbol": "FPT",
        "date_from": date(2024, 1, 1),
        "date_to": date(2024, 12, 31),
        "template_id": "sma_crossover",
        "template_params": {"fast_window": 20, "slow_window": 50},
    }
    payload.update(overrides)
    return BacktestRunRequest(**payload)


def _bar(time: str) -> BacktestBar:
    return BacktestBar(
        time=time,
        open=10.0,
        high=10.0,
        low=10.0,
        close=10.0,
        volume=1000.0,
    )


def _response() -> BacktestRunResponse:
    return BacktestRunResponse(
        summary_metrics=BacktestSummaryMetrics(
            symbol="FPT",
            template_id="sma_crossover",
            timeframe="1D",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            initial_capital=100_000_000,
            ending_equity=120_000_000,
            total_trades=2,
        ),
        performance_metrics=BacktestPerformanceMetrics(
            total_return_pct=20.0,
            annualized_return_pct=18.0,
            max_drawdown_pct=5.0,
            win_rate_pct=50.0,
            profit_factor=1.5,
            avg_win_pct=10.0,
            avg_loss_pct=-4.0,
            expectancy=3.0,
        ),
        trade_log=[],
        equity_curve=[],
    )


@pytest.mark.asyncio
async def test_backtest_service_orchestrates_request_data_template_engine_and_metrics() -> None:
    request = _request()
    bars = [_bar("2024-01-01"), _bar("2024-01-02")]
    signals = [
        BacktestSignal(
            bar_index=0,
            time="2024-01-01",
            action="buy",
            reason="entry",
        )
    ]
    engine_result = BacktestEngineResult(trade_log=[], equity_curve=[])
    data_service = _FakeDataService(bars)
    template_registry = _FakeTemplateRegistry(
        minimum_history_bars=51,
        signals=signals,
    )
    engine = _FakeEngine(engine_result)
    metrics_builder = _FakeMetricsBuilder(_response())
    service = BacktestService(
        data_service=data_service,
        template_registry=template_registry,
        engine=engine,
        metrics_builder=metrics_builder,
    )

    response = await service.run_backtest(request)

    assert response.summary_metrics.ending_equity == 120_000_000
    assert data_service.calls[0][1] == 51
    assert template_registry.required_calls[0][0] == "sma_crossover"
    assert template_registry.signal_calls[0][1] == bars
    assert engine.calls[0][1] == bars
    assert engine.calls[0][2] == signals
    assert metrics_builder.calls[0] == (request, engine_result)


@pytest.mark.asyncio
async def test_backtest_service_accepts_mapping_request_and_normalizes_it() -> None:
    bars = [_bar("2024-01-01"), _bar("2024-01-02")]
    engine_result = BacktestEngineResult(trade_log=[], equity_curve=[])
    data_service = _FakeDataService(bars)
    template_registry = _FakeTemplateRegistry(minimum_history_bars=1, signals=[])
    engine = _FakeEngine(engine_result)
    metrics_builder = _FakeMetricsBuilder(_response())
    service = BacktestService(
        data_service=data_service,
        template_registry=template_registry,
        engine=engine,
        metrics_builder=metrics_builder,
    )

    await service.run_backtest(
        {
            "symbol": " fpt ",
            "date_from": date(2024, 1, 1),
            "date_to": date(2024, 12, 31),
        }
    )

    assert data_service.calls[0][0].symbol == "FPT"
    assert data_service.calls[0][0].template_id == "buy_and_hold"


@pytest.mark.asyncio
async def test_backtest_service_stops_before_template_engine_and_metrics_when_data_loading_fails() -> (
    None
):
    data_service = _FakeDataService([], error=ValueError("history failed"))
    template_registry = _FakeTemplateRegistry(minimum_history_bars=1, signals=[])
    engine = _FakeEngine(BacktestEngineResult(trade_log=[], equity_curve=[]))
    metrics_builder = _FakeMetricsBuilder(_response())
    service = BacktestService(
        data_service=data_service,
        template_registry=template_registry,
        engine=engine,
        metrics_builder=metrics_builder,
    )

    with pytest.raises(ValueError, match="history failed"):
        await service.run_backtest(_request())

    assert len(data_service.calls) == 1
    assert template_registry.signal_calls == []
    assert engine.calls == []
    assert metrics_builder.calls == []


@pytest.mark.asyncio
async def test_backtest_service_offloads_cpu_bound_steps_to_threadpool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    bars = [_bar("2024-01-01"), _bar("2024-01-02")]
    signals = [
        BacktestSignal(
            bar_index=0,
            time="2024-01-01",
            action="buy",
            reason="entry",
        )
    ]
    engine_result = BacktestEngineResult(trade_log=[], equity_curve=[])
    expected_response = _response()
    data_service = _FakeDataService(bars)
    template_registry = _FakeTemplateRegistry(
        minimum_history_bars=2,
        signals=signals,
    )
    engine = _FakeEngine(engine_result)
    metrics_builder = _FakeMetricsBuilder(expected_response)
    service = BacktestService(
        data_service=data_service,
        template_registry=template_registry,
        engine=engine,
        metrics_builder=metrics_builder,
    )
    threadpool_calls: list[tuple[str, tuple[object, ...]]] = []

    async def _fake_to_thread(func, /, *args, **kwargs):
        assert kwargs == {}
        threadpool_calls.append((func.__qualname__, args))
        return func(*args)

    monkeypatch.setattr(backtest_service_module.asyncio, "to_thread", _fake_to_thread)

    response = await service.run_backtest(request)

    assert response == expected_response
    assert [name for name, _ in threadpool_calls] == [
        _FakeTemplateRegistry.generate_signals.__qualname__,
        _FakeEngine.run.__qualname__,
        _FakeMetricsBuilder.build_response.__qualname__,
    ]
    assert threadpool_calls[0][1] == ("sma_crossover", bars, request.template_params)
    assert threadpool_calls[1][1] == (request, bars, signals)
    assert threadpool_calls[2][1] == (request, engine_result)
