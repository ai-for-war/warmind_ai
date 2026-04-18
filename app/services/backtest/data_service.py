"""Data-loading helpers for backtest runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pydantic import ValidationError

from app.domain.schemas.backtest import BacktestBar, BacktestRunRequest
from app.domain.schemas.stock_price import StockPriceHistoryQuery
from app.services.stocks.price_service import StockPriceService

_LOOKBACK_DAY_MULTIPLIER = 2


@dataclass(frozen=True)
class BacktestBarWindow:
    """Canonical bars split into warmup and tradable backtest windows."""

    all_bars: list[BacktestBar]
    warmup_bars: list[BacktestBar]
    tradable_bars: list[BacktestBar]


class BacktestDataService:
    """Load canonical market data for backtest execution."""

    def __init__(self, stock_price_service: StockPriceService) -> None:
        self.stock_price_service = stock_price_service

    async def load_bars(
        self,
        request: BacktestRunRequest,
        *,
        minimum_history_bars: int = 1,
        minimum_tradable_bars: int | None = None,
    ) -> BacktestBarWindow:
        """Load canonical daily bars and split warmup from tradable history."""
        if minimum_history_bars <= 0:
            raise ValueError("minimum_history_bars must be greater than zero")
        if minimum_tradable_bars is None:
            minimum_tradable_bars = minimum_history_bars
        if minimum_tradable_bars <= 0:
            raise ValueError("minimum_tradable_bars must be greater than zero")

        warmup_bars_required = max(minimum_history_bars - 1, 0)
        history = await self.stock_price_service.get_history(
            request.symbol,
            StockPriceHistoryQuery(
                start=self._expand_history_start(
                    request.date_from,
                    warmup_bars_required=warmup_bars_required,
                ).isoformat(),
                end=request.date_to.isoformat(),
                interval=request.timeframe,
            ),
        )
        bars = self._to_backtest_bars(history.items)
        window = self._split_bar_window(
            bars,
            date_from=request.date_from,
            date_to=request.date_to,
        )
        if not window.tradable_bars:
            raise ValueError("No tradable daily history is available in the requested backtest window")
        if len(window.warmup_bars) + 1 < minimum_history_bars:
            raise ValueError(
                "Not enough pre-window daily history to satisfy the selected backtest template"
            )
        if len(window.tradable_bars) < minimum_tradable_bars:
            raise ValueError(
                "Not enough tradable daily history to execute the selected backtest template"
            )
        return window

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

    @classmethod
    def _expand_history_start(
        cls,
        requested_start: date,
        *,
        warmup_bars_required: int,
    ) -> date:
        """Shift the upstream start date backward far enough to try loading warmup bars."""
        if warmup_bars_required <= 0:
            return requested_start
        lookback_days = warmup_bars_required * _LOOKBACK_DAY_MULTIPLIER
        return requested_start - timedelta(days=lookback_days)

    @classmethod
    def _split_bar_window(
        cls,
        bars: list[BacktestBar],
        *,
        date_from: date,
        date_to: date,
    ) -> BacktestBarWindow:
        """Partition ordered bars into pre-window warmup and tradable slices."""
        warmup_bars: list[BacktestBar] = []
        tradable_bars: list[BacktestBar] = []

        for bar in bars:
            bar_date = cls._parse_bar_date(bar.time)
            if bar_date < date_from:
                warmup_bars.append(bar)
                continue
            if bar_date > date_to:
                continue
            tradable_bars.append(bar)

        return BacktestBarWindow(
            all_bars=warmup_bars + tradable_bars,
            warmup_bars=warmup_bars,
            tradable_bars=tradable_bars,
        )

    @staticmethod
    def _parse_bar_date(value: str) -> date:
        """Parse a bar timestamp into a date for warmup window partitioning."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Stock price history contains invalid backtest bars")
        if len(normalized) == 10:
            return date.fromisoformat(normalized)
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
