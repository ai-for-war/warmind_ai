"""Top-level orchestration service for internal backtests."""

from __future__ import annotations

import asyncio

from app.domain.schemas.backtest import BacktestRunRequest, BacktestRunResponse
from app.services.backtest.data_service import BacktestDataService
from app.services.backtest.engine import BacktestEngine
from app.services.backtest.metrics import BacktestMetricsBuilder
from app.services.backtest.templates import BacktestTemplateRegistry


class BacktestService:
    """Coordinate request validation, execution, and result shaping."""

    def __init__(
        self,
        data_service: BacktestDataService,
        template_registry: BacktestTemplateRegistry,
        engine: BacktestEngine,
        metrics_builder: BacktestMetricsBuilder,
    ) -> None:
        self.data_service = data_service
        self.template_registry = template_registry
        self.engine = engine
        self.metrics_builder = metrics_builder

    async def run_backtest(
        self,
        request: BacktestRunRequest | dict[str, object],
    ) -> BacktestRunResponse:
        """Run one full internal backtest from request validation to response."""
        normalized_request = BacktestRunRequest.model_validate(request)
        minimum_history_bars = self.template_registry.required_history_bars(
            normalized_request.template_id,
            normalized_request.template_params,
        )
        bar_window = await self.data_service.load_bars(
            normalized_request,
            minimum_history_bars=minimum_history_bars,
            minimum_tradable_bars=1,
        )
        bars = bar_window.tradable_bars
        signals = await asyncio.to_thread(
            self.template_registry.generate_signals,
            normalized_request.template_id,
            bar_window.all_bars,
            normalized_request.template_params,
            tradable_start_index=len(bar_window.warmup_bars),
        )
        execution_result = await asyncio.to_thread(
            self.engine.run,
            normalized_request,
            bars,
            signals,
        )
        return await asyncio.to_thread(
            self.metrics_builder.build_response,
            normalized_request,
            execution_result,
        )
