"""Technical indicator computation tool for the technical analyst runtime."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
from langchain_core.tools import StructuredTool
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator

from app.agents.implementations.technical_analyst.tools.dependencies import (
    get_stock_price_service,
)
from app.domain.schemas.stock_price import StockPriceHistoryItem
from app.domain.schemas.technical_analysis import (
    ComputeTechnicalIndicatorsInput,
    TechnicalBollingerConfig,
    TechnicalIndicatorConfig,
    TechnicalIndicatorReading,
    TechnicalIndicatorSnapshot,
    TechnicalMacdConfig,
    TechnicalPriceLevel,
    TechnicalSignalDirection,
)
from app.services.stocks.price_service import StockPriceService

IndicatorSignalResolver = Callable[[float], TechnicalSignalDirection | None]

_CORE_CONFIG = TechnicalIndicatorConfig(
    sma_windows=[20, 50, 200],
    ema_windows=[20],
    rsi_windows=[14],
    macd=TechnicalMacdConfig(fast_window=12, slow_window=26, signal_window=9),
    bollinger=TechnicalBollingerConfig(window=20, window_dev=2.0),
    atr_window=14,
    adx_window=14,
    volume_average_windows=[20],
    include_obv=True,
    include_support_resistance=True,
)
_TREND_CONFIG = TechnicalIndicatorConfig(
    sma_windows=[20, 50, 200],
    ema_windows=[20],
    adx_window=14,
    include_support_resistance=True,
)
_MOMENTUM_CONFIG = TechnicalIndicatorConfig(
    rsi_windows=[14],
    macd=TechnicalMacdConfig(fast_window=12, slow_window=26, signal_window=9),
)
_VOLATILITY_CONFIG = TechnicalIndicatorConfig(
    bollinger=TechnicalBollingerConfig(window=20, window_dev=2.0),
    atr_window=14,
    include_support_resistance=True,
)
_VOLUME_CONFIG = TechnicalIndicatorConfig(
    volume_average_windows=[20],
    include_obv=True,
)


async def compute_technical_indicators_result(
    request: ComputeTechnicalIndicatorsInput | dict[str, Any],
    *,
    stock_price_service: StockPriceService | None = None,
) -> TechnicalIndicatorSnapshot:
    """Load canonical OHLCV and compute normalized indicator evidence."""
    normalized_request = ComputeTechnicalIndicatorsInput.model_validate(request)
    service = stock_price_service or get_stock_price_service()
    history = await service.get_history(
        normalized_request.symbol,
        normalized_request.to_stock_price_history_query(),
    )
    frame = _history_to_frame(history.items)
    config = _resolve_indicator_config(normalized_request)
    return _compute_indicator_snapshot(
        normalized_request,
        source=history.source,
        items=history.items,
        frame=frame,
        config=config,
    )


async def _compute_technical_indicators_tool(**kwargs: Any) -> dict[str, Any]:
    snapshot = await compute_technical_indicators_result(kwargs)
    return snapshot.model_dump(mode="json")


compute_technical_indicators = StructuredTool.from_function(
    coroutine=_compute_technical_indicators_tool,
    name="compute_technical_indicators",
    description=(
        "Self-contained technical indicator computation. The tool loads canonical "
        "daily OHLCV history through the stock price service and computes the "
        "requested preset or custom indicator package. The agent only supplies "
        "symbol, history query fields, and indicator configuration; it must not "
        "call load_price_history first or pass raw OHLCV into this tool."
    ),
    args_schema=ComputeTechnicalIndicatorsInput,
)


def _compute_indicator_snapshot(
    request: ComputeTechnicalIndicatorsInput,
    *,
    source: str,
    items: list[StockPriceHistoryItem],
    frame: pd.DataFrame,
    config: TechnicalIndicatorConfig,
) -> TechnicalIndicatorSnapshot:
    unavailable: list[str] = []
    trend: list[TechnicalIndicatorReading] = []
    momentum: list[TechnicalIndicatorReading] = []
    volatility: list[TechnicalIndicatorReading] = []
    volume: list[TechnicalIndicatorReading] = []
    support_levels: list[TechnicalPriceLevel] = []
    resistance_levels: list[TechnicalPriceLevel] = []

    close = frame["close"] if "close" in frame else pd.Series(dtype="float64")
    high = frame["high"] if "high" in frame else pd.Series(dtype="float64")
    low = frame["low"] if "low" in frame else pd.Series(dtype="float64")
    current_volume = frame["volume"] if "volume" in frame else pd.Series(dtype="float64")

    for window in config.sma_windows:
        _append_indicator_reading(
            trend,
            unavailable,
            name=f"sma_{window}",
            series_factory=lambda window=window: SMAIndicator(
                close=close,
                window=window,
                fillna=False,
            ).sma_indicator(),
            signal_resolver=lambda value: _price_position_signal(close, value),
            interpretation_factory=lambda value, window=window: (
                f"Latest close is {_format_price_position(close, value)} SMA{window}."
            ),
        )

    for window in config.ema_windows:
        _append_indicator_reading(
            trend,
            unavailable,
            name=f"ema_{window}",
            series_factory=lambda window=window: EMAIndicator(
                close=close,
                window=window,
                fillna=False,
            ).ema_indicator(),
            signal_resolver=lambda value: _price_position_signal(close, value),
            interpretation_factory=lambda value, window=window: (
                f"Latest close is {_format_price_position(close, value)} EMA{window}."
            ),
        )

    if config.adx_window is not None:
        adx_name = f"adx_{config.adx_window}"
        plus_di_name = f"plus_di_{config.adx_window}"
        minus_di_name = f"minus_di_{config.adx_window}"
        adx = _safe_indicator_series(
            adx_name,
            unavailable,
            lambda: ADXIndicator(
                high=high,
                low=low,
                close=close,
                window=config.adx_window,
                fillna=False,
            ).adx(),
        )
        adx_pos = _safe_indicator_series(
            plus_di_name,
            unavailable,
            lambda: ADXIndicator(
                high=high,
                low=low,
                close=close,
                window=config.adx_window,
                fillna=False,
            ).adx_pos(),
        )
        adx_neg = _safe_indicator_series(
            minus_di_name,
            unavailable,
            lambda: ADXIndicator(
                high=high,
                low=low,
                close=close,
                window=config.adx_window,
                fillna=False,
            ).adx_neg(),
        )
        _append_latest_reading(
            trend,
            unavailable,
            name=adx_name,
            series=adx,
            signal=_adx_signal(adx_pos, adx_neg),
            interpretation_factory=lambda value: (
                "ADX indicates a strong trend."
                if value >= 25
                else "ADX does not indicate a strong trend."
            ),
        )
        _append_latest_reading(trend, unavailable, name=plus_di_name, series=adx_pos)
        _append_latest_reading(trend, unavailable, name=minus_di_name, series=adx_neg)

    for window in config.rsi_windows:
        _append_indicator_reading(
            momentum,
            unavailable,
            name=f"rsi_{window}",
            series_factory=lambda window=window: RSIIndicator(
                close=close,
                window=window,
                fillna=False,
            ).rsi(),
            signal_resolver=_rsi_signal,
            interpretation_factory=_rsi_interpretation,
        )

    if config.macd is not None:
        macd_indicator = MACD(
            close=close,
            window_fast=config.macd.fast_window,
            window_slow=config.macd.slow_window,
            window_sign=config.macd.signal_window,
            fillna=False,
        )
        macd_name = (
            f"macd_{config.macd.fast_window}_"
            f"{config.macd.slow_window}_{config.macd.signal_window}"
        )
        macd_line = _safe_indicator_series(macd_name, unavailable, macd_indicator.macd)
        macd_signal = _safe_indicator_series(
            "macd_signal",
            unavailable,
            macd_indicator.macd_signal,
        )
        macd_histogram = _safe_indicator_series(
            "macd_histogram",
            unavailable,
            macd_indicator.macd_diff,
        )
        _append_latest_reading(
            momentum,
            unavailable,
            name=macd_name,
            series=macd_line,
            signal=_macd_signal(macd_histogram),
            interpretation_factory=lambda value: (
                "MACD line is above zero."
                if value > 0
                else "MACD line is below zero."
            ),
        )
        _append_latest_reading(momentum, unavailable, name="macd_signal", series=macd_signal)
        _append_latest_reading(
            momentum,
            unavailable,
            name="macd_histogram",
            series=macd_histogram,
            signal=_macd_signal(macd_histogram),
        )

    if config.bollinger is not None:
        bollinger = BollingerBands(
            close=close,
            window=config.bollinger.window,
            window_dev=config.bollinger.window_dev,
            fillna=False,
        )
        _append_bollinger_readings(
            volatility,
            unavailable,
            close=close,
            bollinger=bollinger,
            window=config.bollinger.window,
        )

    if config.atr_window is not None:
        _append_indicator_reading(
            volatility,
            unavailable,
            name=f"atr_{config.atr_window}",
            series_factory=lambda: AverageTrueRange(
                high=high,
                low=low,
                close=close,
                window=config.atr_window,
                fillna=False,
            ).average_true_range(),
            interpretation_factory=lambda value: f"ATR is {value:.4f} price units.",
        )

    if config.include_obv:
        obv_series = _safe_indicator_series(
            "obv",
            unavailable,
            lambda: OnBalanceVolumeIndicator(
                close=close,
                volume=current_volume,
                fillna=False,
            ).on_balance_volume(),
        )
        _append_latest_reading(
            volume,
            unavailable,
            name="obv",
            series=obv_series,
            signal=_obv_signal(obv_series),
            interpretation_factory=lambda value: (
                f"OBV latest value is {value:.4f}; compare direction with price trend."
            ),
        )

    for window in config.volume_average_windows:
        _append_indicator_reading(
            volume,
            unavailable,
            name=f"volume_avg_{window}",
            series_factory=lambda window=window: current_volume.rolling(window).mean(),
            signal_resolver=lambda value: _volume_average_signal(current_volume, value),
            interpretation_factory=lambda value, window=window: (
                f"Latest volume is {_format_volume_position(current_volume, value)} "
                f"the {window}-bar average."
            ),
        )

    if config.include_support_resistance:
        support_levels, resistance_levels = _derive_support_resistance(frame, unavailable)

    return TechnicalIndicatorSnapshot(
        symbol=request.symbol,
        interval=request.interval,
        source=source,  # type: ignore[arg-type]
        bars_loaded=len(items),
        as_of=_latest_time(items),
        indicator_set=request.indicator_set,
        trend=trend,
        momentum=momentum,
        volatility=volatility,
        volume=volume,
        support_levels=support_levels,
        resistance_levels=resistance_levels,
        unavailable_indicators=_dedupe(unavailable),
    )


def _append_bollinger_readings(
    target: list[TechnicalIndicatorReading],
    unavailable: list[str],
    *,
    close: pd.Series,
    bollinger: BollingerBands,
    window: int,
) -> None:
    _append_latest_reading(
        target,
        unavailable,
        name=f"bollinger_upper_{window}",
        series=_safe_indicator_series(
            f"bollinger_upper_{window}",
            unavailable,
            bollinger.bollinger_hband,
        ),
        signal_resolver=lambda value: _bollinger_band_signal(close, value, "upper"),
        interpretation_factory=lambda value: (
            f"Latest close is {_format_price_position(close, value)} the upper band."
        ),
    )
    _append_latest_reading(
        target,
        unavailable,
        name=f"bollinger_middle_{window}",
        series=_safe_indicator_series(
            f"bollinger_middle_{window}",
            unavailable,
            bollinger.bollinger_mavg,
        ),
        signal_resolver=lambda value: _price_position_signal(close, value),
    )
    _append_latest_reading(
        target,
        unavailable,
        name=f"bollinger_lower_{window}",
        series=_safe_indicator_series(
            f"bollinger_lower_{window}",
            unavailable,
            bollinger.bollinger_lband,
        ),
        signal_resolver=lambda value: _bollinger_band_signal(close, value, "lower"),
        interpretation_factory=lambda value: (
            f"Latest close is {_format_price_position(close, value)} the lower band."
        ),
    )
    _append_latest_reading(
        target,
        unavailable,
        name=f"bollinger_width_{window}",
        series=_safe_indicator_series(
            f"bollinger_width_{window}",
            unavailable,
            bollinger.bollinger_wband,
        ),
    )


def _resolve_indicator_config(
    request: ComputeTechnicalIndicatorsInput,
) -> TechnicalIndicatorConfig:
    if request.indicator_set == "custom":
        if request.config is None:
            raise ValueError("config is required when indicator_set is custom")
        return request.config
    if request.indicator_set == "trend":
        return _TREND_CONFIG.model_copy(deep=True)
    if request.indicator_set == "momentum":
        return _MOMENTUM_CONFIG.model_copy(deep=True)
    if request.indicator_set == "volatility":
        return _VOLATILITY_CONFIG.model_copy(deep=True)
    if request.indicator_set == "volume":
        return _VOLUME_CONFIG.model_copy(deep=True)
    return _CORE_CONFIG.model_copy(deep=True)


def _history_to_frame(items: list[StockPriceHistoryItem]) -> pd.DataFrame:
    frame = pd.DataFrame([item.model_dump(mode="json") for item in items])
    expected_columns = ["time", "open", "high", "low", "close", "volume"]
    for column in expected_columns:
        if column not in frame:
            frame[column] = None
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[expected_columns]


def _append_indicator_reading(
    target: list[TechnicalIndicatorReading],
    unavailable: list[str],
    *,
    name: str,
    series_factory: Callable[[], pd.Series],
    signal_resolver: IndicatorSignalResolver | None = None,
    interpretation_factory: Callable[[float], str | None] | None = None,
) -> None:
    _append_latest_reading(
        target,
        unavailable,
        name=name,
        series=_safe_indicator_series(name, unavailable, series_factory),
        signal_resolver=signal_resolver,
        interpretation_factory=interpretation_factory,
    )


def _append_latest_reading(
    target: list[TechnicalIndicatorReading],
    unavailable: list[str],
    *,
    name: str,
    series: pd.Series | None,
    signal: TechnicalSignalDirection | None = None,
    signal_resolver: IndicatorSignalResolver | None = None,
    interpretation_factory: Callable[[float], str | None] | None = None,
) -> None:
    value = _latest_finite(series)
    if value is None:
        unavailable.append(name)
        return
    resolved_signal = signal if signal is not None else None
    if signal_resolver is not None:
        resolved_signal = signal_resolver(value)
    target.append(
        TechnicalIndicatorReading(
            name=name,
            value=_round_float(value),
            signal=resolved_signal,
            interpretation=(
                interpretation_factory(value)
                if interpretation_factory is not None
                else None
            ),
        )
    )


def _safe_indicator_series(
    name: str,
    unavailable: list[str],
    factory: Callable[[], pd.Series],
) -> pd.Series | None:
    try:
        return factory()
    except Exception:
        unavailable.append(name)
        return None


def _derive_support_resistance(
    frame: pd.DataFrame,
    unavailable: list[str],
) -> tuple[list[TechnicalPriceLevel], list[TechnicalPriceLevel]]:
    if len(frame) < 5:
        unavailable.append("support_resistance")
        return [], []

    levels: list[tuple[int, pd.DataFrame]] = [(min(20, len(frame)), frame.tail(20))]
    if len(frame) >= 60:
        levels.append((60, frame.tail(60)))

    support_levels: list[TechnicalPriceLevel] = []
    resistance_levels: list[TechnicalPriceLevel] = []
    for window, window_frame in levels:
        lows = window_frame["low"].dropna()
        highs = window_frame["high"].dropna()
        if lows.empty or highs.empty:
            continue
        support_levels.append(
            TechnicalPriceLevel(
                label=f"{window}_bar_low",
                price=_round_float(float(lows.min())),
                rationale=f"Lowest low in the latest {window} daily bars.",
            )
        )
        resistance_levels.append(
            TechnicalPriceLevel(
                label=f"{window}_bar_high",
                price=_round_float(float(highs.max())),
                rationale=f"Highest high in the latest {window} daily bars.",
            )
        )

    if not support_levels or not resistance_levels:
        unavailable.append("support_resistance")
    return support_levels, resistance_levels


def _latest_time(items: list[StockPriceHistoryItem]) -> str | None:
    for item in reversed(items):
        if item.time:
            return item.time
    return None


def _latest_finite(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    value = series.iloc[-1]
    if pd.isna(value):
        return None
    parsed = float(value)
    if not pd.notna(parsed):
        return None
    return parsed


def _previous_finite(series: pd.Series | None) -> float | None:
    if series is None or len(series) < 2:
        return None
    previous = series.iloc[-2]
    if pd.isna(previous):
        return None
    return float(previous)


def _price_position_signal(
    close: pd.Series,
    indicator_value: float,
) -> TechnicalSignalDirection:
    current_close = _latest_finite(close)
    if current_close is None:
        return "unclear"
    if current_close > indicator_value:
        return "bullish"
    if current_close < indicator_value:
        return "bearish"
    return "neutral"


def _format_price_position(close: pd.Series, indicator_value: float) -> str:
    signal = _price_position_signal(close, indicator_value)
    if signal == "bullish":
        return "above"
    if signal == "bearish":
        return "below"
    return "at"


def _rsi_signal(value: float) -> TechnicalSignalDirection:
    if value >= 70:
        return "bearish"
    if value <= 30:
        return "bullish"
    if value > 50:
        return "bullish"
    if value < 50:
        return "bearish"
    return "neutral"


def _rsi_interpretation(value: float) -> str:
    if value >= 70:
        return "RSI is in an overbought zone."
    if value <= 30:
        return "RSI is in an oversold zone."
    if value > 50:
        return "RSI is above the neutral 50 line."
    if value < 50:
        return "RSI is below the neutral 50 line."
    return "RSI is neutral."


def _macd_signal(series: pd.Series | None) -> TechnicalSignalDirection:
    value = _latest_finite(series)
    if value is None:
        return "unclear"
    if value > 0:
        return "bullish"
    if value < 0:
        return "bearish"
    return "neutral"


def _adx_signal(
    adx_pos: pd.Series | None,
    adx_neg: pd.Series | None,
) -> TechnicalSignalDirection:
    plus_di = _latest_finite(adx_pos)
    minus_di = _latest_finite(adx_neg)
    if plus_di is None or minus_di is None:
        return "unclear"
    if plus_di > minus_di:
        return "bullish"
    if plus_di < minus_di:
        return "bearish"
    return "neutral"


def _bollinger_band_signal(
    close: pd.Series,
    band_value: float,
    band: str,
) -> TechnicalSignalDirection:
    current_close = _latest_finite(close)
    if current_close is None:
        return "unclear"
    if band == "upper" and current_close >= band_value:
        return "bearish"
    if band == "lower" and current_close <= band_value:
        return "bullish"
    return "neutral"


def _obv_signal(series: pd.Series | None) -> TechnicalSignalDirection:
    current = _latest_finite(series)
    previous = _previous_finite(series)
    if current is None or previous is None:
        return "unclear"
    if current > previous:
        return "bullish"
    if current < previous:
        return "bearish"
    return "neutral"


def _volume_average_signal(
    volume: pd.Series,
    average_volume: float,
) -> TechnicalSignalDirection:
    current_volume = _latest_finite(volume)
    if current_volume is None:
        return "unclear"
    if current_volume > average_volume:
        return "bullish"
    if current_volume < average_volume:
        return "bearish"
    return "neutral"


def _format_volume_position(volume: pd.Series, average_volume: float) -> str:
    signal = _volume_average_signal(volume, average_volume)
    if signal == "bullish":
        return "above"
    if signal == "bearish":
        return "below"
    return "at"


def _round_float(value: float) -> float:
    return round(float(value), 4)


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
