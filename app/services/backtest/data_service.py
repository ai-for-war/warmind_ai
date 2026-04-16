"""Data-loading helpers for backtest runs."""

from __future__ import annotations

from pydantic import ValidationError

from app.domain.schemas.backtest import BacktestBar, BacktestRunRequest
from app.domain.schemas.stock_price import StockPriceHistoryQuery
from app.services.stocks.price_service import StockPriceService


class BacktestDataService:
    """Load canonical market data for backtest execution."""

    def __init__(self, stock_price_service: StockPriceService) -> None:
        self.stock_price_service = stock_price_service

    async def load_bars(
        self,
        request: BacktestRunRequest,
        *,
        minimum_history_bars: int = 1,
    ) -> list[BacktestBar]:
        """Load ordered canonical daily bars for one backtest request."""
        if minimum_history_bars <= 0:
            raise ValueError("minimum_history_bars must be greater than zero")

        history = await self.stock_price_service.get_history(
            request.symbol,
            StockPriceHistoryQuery(
                start=request.date_from.isoformat(),
                end=request.date_to.isoformat(),
                interval=request.timeframe,
            ),
        )
        bars = self._to_backtest_bars(history.items)
        if len(bars) < minimum_history_bars:
            raise ValueError(
                "Not enough daily history to execute the selected backtest template"
            )
        return bars

    @staticmethod
    def _to_backtest_bars(items: list[object]) -> list[BacktestBar]:
        """Convert normalized history items into ordered backtest bars."""
        try:
            bars = [
                BacktestBar.model_validate(
                    item.model_dump() if hasattr(item, "model_dump") else item
                )
                for item in items
            ]
        except ValidationError as exc:
            raise ValueError("Stock price history contains invalid backtest bars") from exc
        return sorted(bars, key=lambda bar: bar.time)
