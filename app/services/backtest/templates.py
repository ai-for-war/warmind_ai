"""Template registration helpers for backtest strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.domain.schemas.backtest import (
    BacktestBar,
    BacktestTemplateId,
    BacktestTemplateParams,
    BuyAndHoldTemplateParams,
    IchimokuCloudTemplateParams,
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


@dataclass(frozen=True)
class BacktestWarningState:
    """One non-executing warning state detected for a specific tradable bar."""

    bar_index: int
    time: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class _IchimokuSeries:
    """Aligned Ichimoku indicator series for one ordered bar history."""

    tenkan: list[float | None]
    kijun: list[float | None]
    aligned_span_a: list[float | None]
    aligned_span_b: list[float | None]


class BacktestTemplate(Protocol):
    """Runtime contract implemented by one backtest template."""

    template_id: BacktestTemplateId

    def required_history_bars(self, params: BacktestTemplateParams) -> int: ...

    def generate_signals(
        self,
        bars: list[BacktestBar],
        params: BacktestTemplateParams,
        *,
        tradable_start_index: int = 0,
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
        *,
        tradable_start_index: int = 0,
    ) -> list[BacktestSignal]:
        self._require_params(params)
        _validate_tradable_start_index(bars, tradable_start_index)
        if tradable_start_index >= len(bars):
            return []
        return [
            BacktestSignal(
                bar_index=0,
                time=bars[tradable_start_index].time,
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
        *,
        tradable_start_index: int = 0,
    ) -> list[BacktestSignal]:
        resolved_params = self._require_params(params)
        _validate_tradable_start_index(bars, tradable_start_index)
        if len(bars) < self.required_history_bars(resolved_params):
            return []

        fast_values = _rolling_sma(bars, resolved_params.fast_window)
        slow_values = _rolling_sma(bars, resolved_params.slow_window)
        signals: list[BacktestSignal] = []

        for index in range(max(1, tradable_start_index), len(bars)):
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
                        bar_index=index - tradable_start_index,
                        time=bars[index].time,
                        action="buy",
                        reason="sma_fast_crosses_above_sma_slow",
                    )
                )
                continue
            if previous_fast >= previous_slow and current_fast < current_slow:
                signals.append(
                    BacktestSignal(
                        bar_index=index - tradable_start_index,
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


class IchimokuCloudTemplate:
    """Generate trend-following signals from aligned Ichimoku cloud rules."""

    template_id: BacktestTemplateId = "ichimoku_cloud"

    def required_history_bars(self, params: BacktestTemplateParams) -> int:
        resolved_params = self._require_params(params)
        return resolved_params.warmup_bars + 1

    def generate_signals(
        self,
        bars: list[BacktestBar],
        params: BacktestTemplateParams,
        *,
        tradable_start_index: int = 0,
    ) -> list[BacktestSignal]:
        return self._evaluate_bars(
            bars,
            params,
            tradable_start_index=tradable_start_index,
        )[0]

    def evaluate_warning_states(
        self,
        bars: list[BacktestBar],
        params: BacktestTemplateParams,
        *,
        tradable_start_index: int = 0,
    ) -> list[BacktestWarningState]:
        return self._evaluate_bars(
            bars,
            params,
            tradable_start_index=tradable_start_index,
        )[1]

    def _evaluate_bars(
        self,
        bars: list[BacktestBar],
        params: BacktestTemplateParams,
        *,
        tradable_start_index: int,
    ) -> tuple[list[BacktestSignal], list[BacktestWarningState]]:
        resolved_params = self._require_params(params)
        _validate_tradable_start_index(bars, tradable_start_index)
        if tradable_start_index >= len(bars):
            return [], []
        if len(bars) < self.required_history_bars(resolved_params):
            return [], []

        series = self._compute_series(bars, resolved_params)
        signals: list[BacktestSignal] = []
        warnings: list[BacktestWarningState] = []

        for index in range(tradable_start_index, len(bars)):
            if self._is_sell_signal(
                bars,
                series,
                resolved_params,
                index,
            ):
                signals.append(
                    BacktestSignal(
                        bar_index=index - tradable_start_index,
                        time=bars[index].time,
                        action="sell",
                        reason=self._sell_reason(
                            bars,
                            series,
                            resolved_params,
                            index,
                        ),
                    )
                )
                continue

            warning_reasons = self._warning_reasons_for_index(
                bars,
                series,
                resolved_params,
                index,
            )
            if warning_reasons:
                warnings.append(
                    BacktestWarningState(
                        bar_index=index - tradable_start_index,
                        time=bars[index].time,
                        reasons=warning_reasons,
                    )
                )

            if self._is_buy_signal(
                bars,
                series,
                resolved_params,
                index,
            ):
                signals.append(
                    BacktestSignal(
                        bar_index=index - tradable_start_index,
                        time=bars[index].time,
                        action="buy",
                        reason="ichimoku_price_above_bullish_cloud_with_bullish_tk_cross",
                    )
                )

        return signals, warnings

    def _compute_series(
        self,
        bars: list[BacktestBar],
        params: IchimokuCloudTemplateParams,
    ) -> _IchimokuSeries:
        tenkan = _rolling_midpoint(bars, params.tenkan_window)
        kijun = _rolling_midpoint(bars, params.kijun_window)
        raw_span_a: list[float | None] = []
        for tenkan_value, kijun_value in zip(tenkan, kijun, strict=False):
            if tenkan_value is None or kijun_value is None:
                raw_span_a.append(None)
                continue
            raw_span_a.append((tenkan_value + kijun_value) / 2)

        raw_span_b = _rolling_midpoint(bars, params.senkou_b_window)

        return _IchimokuSeries(
            tenkan=tenkan,
            kijun=kijun,
            aligned_span_a=_align_shifted_series(raw_span_a, params.displacement),
            aligned_span_b=_align_shifted_series(raw_span_b, params.displacement),
        )

    def _is_buy_signal(
        self,
        bars: list[BacktestBar],
        series: _IchimokuSeries,
        params: IchimokuCloudTemplateParams,
        index: int,
    ) -> bool:
        cloud_top = self._aligned_cloud_top(series, index)
        aligned_span_a = series.aligned_span_a[index]
        aligned_span_b = series.aligned_span_b[index]
        if (
            cloud_top is None
            or aligned_span_a is None
            or aligned_span_b is None
            or aligned_span_a <= aligned_span_b
        ):
            return False
        if bars[index].close <= cloud_top:
            return False
        if not self._is_bullish_tk_cross(series, index):
            return False
        return self._is_chikou_confirmed(bars, params, index)

    def _is_sell_signal(
        self,
        bars: list[BacktestBar],
        series: _IchimokuSeries,
        params: IchimokuCloudTemplateParams,
        index: int,
    ) -> bool:
        return self._is_cloud_breakdown(bars, series, index) or self._is_bearish_tk_kijun_loss(
            bars,
            series,
            params,
            index,
        )

    def _sell_reason(
        self,
        bars: list[BacktestBar],
        series: _IchimokuSeries,
        params: IchimokuCloudTemplateParams,
        index: int,
    ) -> str:
        if self._is_cloud_breakdown(bars, series, index):
            return "ichimoku_close_below_aligned_cloud"
        if self._is_bearish_tk_kijun_loss(bars, series, params, index):
            return "ichimoku_bearish_tk_cross_with_kijun_loss"
        raise ValueError("sell_reason requires a confirmed Ichimoku sell signal")

    def _warning_reasons_for_index(
        self,
        bars: list[BacktestBar],
        series: _IchimokuSeries,
        params: IchimokuCloudTemplateParams,
        index: int,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        kijun_value = series.kijun[index]
        if kijun_value is not None and bars[index].close < kijun_value:
            reasons.append("close_below_kijun")
        if self._is_bearish_tk_cross(series, index):
            reasons.append("bearish_tenkan_kijun_cross")
        if not self._is_chikou_confirmed(bars, params, index):
            reasons.append("chikou_confirmation_lost")
        cloud_top = self._aligned_cloud_top(series, index)
        aligned_span_a = series.aligned_span_a[index]
        aligned_span_b = series.aligned_span_b[index]
        if (
            cloud_top is not None
            and aligned_span_a is not None
            and aligned_span_b is not None
            and aligned_span_a <= aligned_span_b
            and bars[index].close > cloud_top
        ):
            reasons.append("aligned_cloud_turns_bearish")
        return tuple(reasons)

    @staticmethod
    def _aligned_cloud_top(series: _IchimokuSeries, index: int) -> float | None:
        aligned_span_a = series.aligned_span_a[index]
        aligned_span_b = series.aligned_span_b[index]
        if aligned_span_a is None or aligned_span_b is None:
            return None
        return max(aligned_span_a, aligned_span_b)

    @staticmethod
    def _aligned_cloud_bottom(series: _IchimokuSeries, index: int) -> float | None:
        aligned_span_a = series.aligned_span_a[index]
        aligned_span_b = series.aligned_span_b[index]
        if aligned_span_a is None or aligned_span_b is None:
            return None
        return min(aligned_span_a, aligned_span_b)

    @staticmethod
    def _is_bullish_tk_cross(series: _IchimokuSeries, index: int) -> bool:
        if index <= 0:
            return False
        previous_tenkan = series.tenkan[index - 1]
        previous_kijun = series.kijun[index - 1]
        current_tenkan = series.tenkan[index]
        current_kijun = series.kijun[index]
        if None in (previous_tenkan, previous_kijun, current_tenkan, current_kijun):
            return False
        return bool(previous_tenkan <= previous_kijun and current_tenkan > current_kijun)

    @staticmethod
    def _is_bearish_tk_cross(series: _IchimokuSeries, index: int) -> bool:
        if index <= 0:
            return False
        previous_tenkan = series.tenkan[index - 1]
        previous_kijun = series.kijun[index - 1]
        current_tenkan = series.tenkan[index]
        current_kijun = series.kijun[index]
        if None in (previous_tenkan, previous_kijun, current_tenkan, current_kijun):
            return False
        return bool(previous_tenkan >= previous_kijun and current_tenkan < current_kijun)

    def _is_cloud_breakdown(
        self,
        bars: list[BacktestBar],
        series: _IchimokuSeries,
        index: int,
    ) -> bool:
        cloud_bottom = self._aligned_cloud_bottom(series, index)
        if cloud_bottom is None:
            return False
        return bars[index].close < cloud_bottom

    def _is_bearish_tk_kijun_loss(
        self,
        bars: list[BacktestBar],
        series: _IchimokuSeries,
        params: IchimokuCloudTemplateParams,
        index: int,
    ) -> bool:
        del params
        kijun_value = series.kijun[index]
        if kijun_value is None:
            return False
        return self._is_bearish_tk_cross(series, index) and bars[index].close < kijun_value

    @staticmethod
    def _is_chikou_confirmed(
        bars: list[BacktestBar],
        params: IchimokuCloudTemplateParams,
        index: int,
    ) -> bool:
        confirmation_index = index - params.displacement
        if confirmation_index < 0:
            return False
        return bars[index].close > bars[confirmation_index].high

    @staticmethod
    def _require_params(params: BacktestTemplateParams) -> IchimokuCloudTemplateParams:
        if not isinstance(params, IchimokuCloudTemplateParams):
            raise TypeError("ichimoku_cloud requires IchimokuCloudTemplateParams")
        return params


class BacktestTemplateRegistry:
    """Resolve supported backtest strategy templates."""

    def __init__(self) -> None:
        self._templates: dict[BacktestTemplateId, BacktestTemplate] = {
            "buy_and_hold": BuyAndHoldTemplate(),
            "sma_crossover": SmaCrossoverTemplate(),
            "ichimoku_cloud": IchimokuCloudTemplate(),
        }

    def get_template(self, template_id: BacktestTemplateId) -> BacktestTemplate:
        """Return one registered template by its stable ID."""
        return self._templates[template_id]

    def supported_template_ids(self) -> tuple[BacktestTemplateId, ...]:
        """Return the currently registered template IDs in stable order."""
        return tuple(self._templates.keys())

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
        *,
        tradable_start_index: int = 0,
    ) -> list[BacktestSignal]:
        """Generate ordered strategy signals for one template."""
        return self.get_template(template_id).generate_signals(
            bars,
            params,
            tradable_start_index=tradable_start_index,
        )


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


def _rolling_midpoint(
    bars: list[BacktestBar],
    window: int,
) -> list[float | None]:
    """Compute midpoint of rolling highest high and lowest low."""
    values: list[float | None] = []
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    for index in range(len(bars)):
        if index + 1 < window:
            values.append(None)
            continue
        high_window = highs[index - window + 1 : index + 1]
        low_window = lows[index - window + 1 : index + 1]
        values.append((max(high_window) + min(low_window)) / 2)
    return values


def _align_shifted_series(
    values: list[float | None],
    displacement: int,
) -> list[float | None]:
    """Align a forward-plotted series back onto the current bar index."""
    aligned: list[float | None] = []
    for index in range(len(values)):
        source_index = index - displacement
        aligned.append(values[source_index] if source_index >= 0 else None)
    return aligned


def _validate_tradable_start_index(
    bars: list[BacktestBar],
    tradable_start_index: int,
) -> None:
    """Validate that the tradable window starts within the provided history."""
    if tradable_start_index < 0:
        raise ValueError("tradable_start_index must not be negative")
    if tradable_start_index > len(bars):
        raise ValueError("tradable_start_index must not exceed the number of bars")
