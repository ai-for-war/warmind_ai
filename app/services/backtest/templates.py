"""Template registration helpers for backtest strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.domain.schemas.backtest import (
    BacktestBar,
    BacktestTemplateId,
    BacktestTemplateParams,
    BuyAndHoldTemplateParams,
    SmaCrossoverTemplateParams,
)

SignalAction = Literal["buy", "sell"]


@dataclass(frozen=True)
class BacktestSignal:
    """One strategy signal emitted for a specific bar."""

    bar_index: int
    time: str
    action: SignalAction
    reason: str


class BacktestTemplate(Protocol):
    """Runtime contract implemented by one backtest template."""

    template_id: BacktestTemplateId

    def required_history_bars(self, params: BacktestTemplateParams) -> int: ...

    def generate_signals(
        self,
        bars: list[BacktestBar],
        params: BacktestTemplateParams,
    ) -> list[BacktestSignal]: ...


class BuyAndHoldTemplate:
    """Buy on the first eligible bar and hold through the backtest window."""

    template_id: BacktestTemplateId = "buy_and_hold"

    def required_history_bars(self, params: BacktestTemplateParams) -> int:
        self._require_params(params)
        return 1

    def generate_signals(
        self,
        bars: list[BacktestBar],
        params: BacktestTemplateParams,
    ) -> list[BacktestSignal]:
        self._require_params(params)
        if not bars:
            return []
        return [
            BacktestSignal(
                bar_index=0,
                time=bars[0].time,
                action="buy",
                reason="buy_and_hold_entry",
            )
        ]

    @staticmethod
    def _require_params(params: BacktestTemplateParams) -> BuyAndHoldTemplateParams:
        if not isinstance(params, BuyAndHoldTemplateParams):
            raise TypeError("buy_and_hold requires BuyAndHoldTemplateParams")
        return params


class SmaCrossoverTemplate:
    """Generate signals from simple moving-average crossover rules."""

    template_id: BacktestTemplateId = "sma_crossover"

    def required_history_bars(self, params: BacktestTemplateParams) -> int:
        resolved_params = self._require_params(params)
        return resolved_params.slow_window + 1

    def generate_signals(
        self,
        bars: list[BacktestBar],
        params: BacktestTemplateParams,
    ) -> list[BacktestSignal]:
        resolved_params = self._require_params(params)
        if len(bars) < self.required_history_bars(resolved_params):
            return []

        fast_values = _rolling_sma(bars, resolved_params.fast_window)
        slow_values = _rolling_sma(bars, resolved_params.slow_window)
        signals: list[BacktestSignal] = []

        for index in range(1, len(bars)):
            previous_fast = fast_values[index - 1]
            previous_slow = slow_values[index - 1]
            current_fast = fast_values[index]
            current_slow = slow_values[index]
            if None in (
                previous_fast,
                previous_slow,
                current_fast,
                current_slow,
            ):
                continue
            if previous_fast <= previous_slow and current_fast > current_slow:
                signals.append(
                    BacktestSignal(
                        bar_index=index,
                        time=bars[index].time,
                        action="buy",
                        reason="sma_fast_crosses_above_sma_slow",
                    )
                )
                continue
            if previous_fast >= previous_slow and current_fast < current_slow:
                signals.append(
                    BacktestSignal(
                        bar_index=index,
                        time=bars[index].time,
                        action="sell",
                        reason="sma_fast_crosses_below_sma_slow",
                    )
                )

        return signals

    @staticmethod
    def _require_params(params: BacktestTemplateParams) -> SmaCrossoverTemplateParams:
        if not isinstance(params, SmaCrossoverTemplateParams):
            raise TypeError("sma_crossover requires SmaCrossoverTemplateParams")
        return params


class BacktestTemplateRegistry:
    """Resolve supported backtest strategy templates."""

    def __init__(self) -> None:
        self._templates: dict[BacktestTemplateId, BacktestTemplate] = {
            "buy_and_hold": BuyAndHoldTemplate(),
            "sma_crossover": SmaCrossoverTemplate(),
        }

    def get_template(self, template_id: BacktestTemplateId) -> BacktestTemplate:
        """Return one registered template by its stable ID."""
        return self._templates[template_id]

    def required_history_bars(
        self,
        template_id: BacktestTemplateId,
        params: BacktestTemplateParams,
    ) -> int:
        """Return the minimum number of bars required to execute a template."""
        return self.get_template(template_id).required_history_bars(params)

    def generate_signals(
        self,
        template_id: BacktestTemplateId,
        bars: list[BacktestBar],
        params: BacktestTemplateParams,
    ) -> list[BacktestSignal]:
        """Generate ordered strategy signals for one template."""
        return self.get_template(template_id).generate_signals(bars, params)


def _rolling_sma(
    bars: list[BacktestBar],
    window: int,
) -> list[float | None]:
    """Compute one rolling simple moving-average series over close prices."""
    values: list[float | None] = []
    closes = [bar.close for bar in bars]
    for index in range(len(closes)):
        if index + 1 < window:
            values.append(None)
            continue
        segment = closes[index - window + 1 : index + 1]
        values.append(sum(segment) / window)
    return values
