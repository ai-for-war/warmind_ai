"""Schemas for internal stock technical-analysis tool contracts."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.domain.schemas.backtest import (
    BacktestRunRequest,
    BacktestTemplateId,
    BacktestTimeframe,
    DEFAULT_BACKTEST_INITIAL_CAPITAL,
    DEFAULT_BACKTEST_TIMEFRAME,
)
from app.domain.schemas.stock import StockSchemaBase
from app.domain.schemas.stock_price import (
    DEFAULT_HISTORY_INTERVAL,
    StockPriceHistoryQuery,
    StockPriceSource,
)

TechnicalAnalysisInterval = Literal["1D"]
TechnicalIndicatorSet = Literal[
    "core",
    "trend",
    "momentum",
    "volatility",
    "volume",
    "custom",
]
TechnicalSignalDirection = Literal["bullish", "bearish", "neutral", "mixed", "unclear"]
TechnicalSignalStrength = Literal["weak", "moderate", "strong"]
TechnicalConfidence = Literal["low", "medium", "high"]

DEFAULT_TECHNICAL_ANALYSIS_INTERVAL: TechnicalAnalysisInterval = "1D"
DEFAULT_TECHNICAL_INDICATOR_SET: TechnicalIndicatorSet = "core"


class TechnicalAnalysisSchema(StockSchemaBase):
    """Base schema for stock technical-analysis payloads."""


class TechnicalMacdConfig(TechnicalAnalysisSchema):
    """Custom MACD window configuration."""

    fast_window: int = Field(default=12, ge=1)
    slow_window: int = Field(default=26, ge=1)
    signal_window: int = Field(default=9, ge=1)

    @model_validator(mode="after")
    def validate_window_order(self) -> "TechnicalMacdConfig":
        """Require MACD fast window to stay below the slow window."""
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be less than slow_window")
        return self


class TechnicalBollingerConfig(TechnicalAnalysisSchema):
    """Custom Bollinger Bands configuration."""

    window: int = Field(default=20, ge=1)
    window_dev: float = Field(default=2.0, gt=0)


class TechnicalIndicatorConfig(TechnicalAnalysisSchema):
    """Custom technical indicator configuration requested by the analyst."""

    sma_windows: list[int] = Field(default_factory=list)
    ema_windows: list[int] = Field(default_factory=list)
    rsi_windows: list[int] = Field(default_factory=list)
    macd: TechnicalMacdConfig | None = None
    bollinger: TechnicalBollingerConfig | None = None
    atr_window: int | None = Field(default=None, ge=1)
    adx_window: int | None = Field(default=None, ge=1)
    volume_average_windows: list[int] = Field(default_factory=list)
    include_obv: bool = False
    include_support_resistance: bool = False

    @field_validator(
        "sma_windows",
        "ema_windows",
        "rsi_windows",
        "volume_average_windows",
        mode="before",
    )
    @classmethod
    def normalize_window_list(cls, values: list[Any] | None) -> list[int]:
        """Normalize requested windows without applying business lookback limits."""
        if values is None:
            return []
        if not isinstance(values, list):
            raise TypeError("indicator windows must be a list")

        normalized_values: list[int] = []
        seen: set[int] = set()
        for value in values:
            if isinstance(value, bool):
                raise TypeError("indicator windows must be integers")
            parsed = int(value)
            if parsed <= 0:
                raise ValueError("indicator windows must be greater than zero")
            if parsed not in seen:
                seen.add(parsed)
                normalized_values.append(parsed)
        return normalized_values

    @model_validator(mode="after")
    def validate_requested_indicator(self) -> "TechnicalIndicatorConfig":
        """Require custom config to request at least one indicator family."""
        has_requested_indicator = any(
            [
                self.sma_windows,
                self.ema_windows,
                self.rsi_windows,
                self.macd is not None,
                self.bollinger is not None,
                self.atr_window is not None,
                self.adx_window is not None,
                self.volume_average_windows,
                self.include_obv,
                self.include_support_resistance,
            ]
        )
        if not has_requested_indicator:
            raise ValueError("custom indicator config must request at least one indicator")
        return self


class TechnicalHistoryToolInput(TechnicalAnalysisSchema):
    """Base stock history query shape shared by technical-analysis tools."""

    symbol: str = Field(..., min_length=1)
    source: StockPriceSource = "VCI"
    interval: TechnicalAnalysisInterval = DEFAULT_TECHNICAL_ANALYSIS_INTERVAL
    length: int | None = Field(default=None, gt=0)
    start: str | None = None
    end: str | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize symbols to the canonical uppercase form used by stock services."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: str | None) -> StockPriceSource:
        """Normalize source text to the supported stock price source values."""
        if value is None:
            return "VCI"
        if not isinstance(value, str):
            raise TypeError("source must be a string")
        normalized = value.strip().upper()
        return normalized or "VCI"  # type: ignore[return-value]

    @field_validator("interval", mode="before")
    @classmethod
    def normalize_interval(cls, value: str | None) -> TechnicalAnalysisInterval:
        """Normalize and constrain phase-one technical analysis to daily bars."""
        if value is None:
            return DEFAULT_TECHNICAL_ANALYSIS_INTERVAL
        if not isinstance(value, str):
            raise TypeError("interval must be a string")
        normalized = value.strip().upper()
        return normalized or DEFAULT_TECHNICAL_ANALYSIS_INTERVAL  # type: ignore[return-value]

    @field_validator("start", "end", mode="before")
    @classmethod
    def normalize_optional_datetime_text(cls, value: str | None) -> str | None:
        """Treat blank date or datetime input as absent."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("datetime query values must be strings")
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_history_mode(self) -> "TechnicalHistoryToolInput":
        """Require either lookback length or explicit range, matching price service."""
        has_start = self.start is not None
        has_length = self.length is not None
        if has_start == has_length:
            raise ValueError("provide exactly one of 'start' or 'length'")
        if self.end is not None and not has_start:
            raise ValueError("'end' is only allowed when 'start' is provided")
        return self

    def to_stock_price_history_query(self) -> StockPriceHistoryQuery:
        """Build the canonical stock price history query used by the price service."""
        return StockPriceHistoryQuery(
            source=self.source,
            start=self.start,
            end=self.end,
            interval=self.interval or DEFAULT_HISTORY_INTERVAL,
            length=self.length,
        )


class ComputeTechnicalIndicatorsInput(TechnicalHistoryToolInput):
    """Input schema for the self-contained technical indicator computation tool."""

    indicator_set: TechnicalIndicatorSet = DEFAULT_TECHNICAL_INDICATOR_SET
    config: TechnicalIndicatorConfig | None = None

    @field_validator("indicator_set", mode="before")
    @classmethod
    def normalize_indicator_set(cls, value: str | None) -> TechnicalIndicatorSet:
        """Normalize indicator set identifiers into stable lowercase values."""
        if value is None:
            return DEFAULT_TECHNICAL_INDICATOR_SET
        if not isinstance(value, str):
            raise TypeError("indicator_set must be a string")
        normalized = value.strip().lower()
        return normalized or DEFAULT_TECHNICAL_INDICATOR_SET  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_custom_config(self) -> "ComputeTechnicalIndicatorsInput":
        """Require explicit config when the custom indicator set is selected."""
        if self.indicator_set == "custom" and self.config is None:
            raise ValueError("config is required when indicator_set is custom")
        return self


class LoadPriceHistoryInput(TechnicalHistoryToolInput):
    """Input schema for optional raw OHLCV inspection."""


class RunTechnicalBacktestInput(TechnicalAnalysisSchema):
    """Input schema for technical analyst access to deterministic backtests."""

    symbol: str = Field(..., min_length=1)
    timeframe: BacktestTimeframe = DEFAULT_BACKTEST_TIMEFRAME
    date_from: date
    date_to: date
    template_id: BacktestTemplateId
    template_params: dict[str, Any] = Field(default_factory=dict)
    initial_capital: int = Field(default=DEFAULT_BACKTEST_INITIAL_CAPITAL, gt=0)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize symbols to the canonical uppercase form used by backtests."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("timeframe", mode="before")
    @classmethod
    def normalize_timeframe(cls, value: str | None) -> BacktestTimeframe:
        """Normalize and constrain phase-one backtests to daily bars."""
        if value is None:
            return DEFAULT_BACKTEST_TIMEFRAME
        if not isinstance(value, str):
            raise TypeError("timeframe must be a string")
        normalized = value.strip().upper()
        return normalized or DEFAULT_BACKTEST_TIMEFRAME  # type: ignore[return-value]

    @field_validator("template_id", mode="before")
    @classmethod
    def normalize_template_id(cls, value: str) -> str:
        """Normalize template identifiers into stable lowercase values."""
        if not isinstance(value, str):
            raise TypeError("template_id must be a string")
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("template_id must not be blank")
        return normalized

    @field_validator("template_params", mode="before")
    @classmethod
    def normalize_template_params(cls, value: object) -> object:
        """Treat blank or omitted template params as an empty object."""
        if value is None or value == "":
            return {}
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "RunTechnicalBacktestInput":
        """Reject inverted backtest date ranges before service execution."""
        if self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        return self

    def to_backtest_run_request(self) -> BacktestRunRequest:
        """Build the canonical internal backtest request."""
        return BacktestRunRequest(
            symbol=self.symbol,
            timeframe=self.timeframe,
            date_from=self.date_from,
            date_to=self.date_to,
            template_id=self.template_id,
            template_params=self.template_params,
            initial_capital=self.initial_capital,
        )


class TechnicalPriceLevel(TechnicalAnalysisSchema):
    """One support, resistance, stop, target, or reference price level."""

    label: str = Field(..., min_length=1)
    price: float = Field(..., ge=0)
    rationale: str | None = None


class TechnicalPriceZone(TechnicalAnalysisSchema):
    """One bounded price zone used by trading plans."""

    label: str = Field(..., min_length=1)
    lower_price: float = Field(..., ge=0)
    upper_price: float = Field(..., ge=0)
    rationale: str | None = None

    @model_validator(mode="after")
    def validate_zone_order(self) -> "TechnicalPriceZone":
        """Require zone upper bound to be at least the lower bound."""
        if self.upper_price < self.lower_price:
            raise ValueError("upper_price must be greater than or equal to lower_price")
        return self


class TechnicalIndicatorReading(TechnicalAnalysisSchema):
    """One normalized indicator reading owned by the backend contract."""

    name: str = Field(..., min_length=1)
    value: float | str | bool | None = None
    signal: TechnicalSignalDirection | None = None
    interpretation: str | None = None


class TechnicalIndicatorSnapshot(TechnicalAnalysisSchema):
    """Structured snapshot returned by technical indicator computation."""

    symbol: str = Field(..., min_length=1)
    interval: TechnicalAnalysisInterval = DEFAULT_TECHNICAL_ANALYSIS_INTERVAL
    source: StockPriceSource = "VCI"
    bars_loaded: int = Field(..., ge=0)
    as_of: str | None = None
    indicator_set: TechnicalIndicatorSet = DEFAULT_TECHNICAL_INDICATOR_SET
    trend: list[TechnicalIndicatorReading] = Field(default_factory=list)
    momentum: list[TechnicalIndicatorReading] = Field(default_factory=list)
    volatility: list[TechnicalIndicatorReading] = Field(default_factory=list)
    volume: list[TechnicalIndicatorReading] = Field(default_factory=list)
    support_levels: list[TechnicalPriceLevel] = Field(default_factory=list)
    resistance_levels: list[TechnicalPriceLevel] = Field(default_factory=list)
    unavailable_indicators: list[str] = Field(default_factory=list)


class TechnicalSignal(TechnicalAnalysisSchema):
    """One technical signal derived from chart and indicator evidence."""

    name: str = Field(..., min_length=1)
    direction: TechnicalSignalDirection
    strength: TechnicalSignalStrength
    evidence: list[str] = Field(default_factory=list)


class TechnicalRisk(TechnicalAnalysisSchema):
    """One technical downside or setup risk."""

    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    severity: TechnicalSignalStrength


class TechnicalUncertainty(TechnicalAnalysisSchema):
    """One missing, stale, conflicting, or scope-limited technical evidence point."""

    description: str = Field(..., min_length=1)


class TechnicalAssessment(TechnicalAnalysisSchema):
    """Narrative assessment for one technical dimension."""

    state: str = Field(..., min_length=1)
    direction: TechnicalSignalDirection = "unclear"
    confidence: TechnicalConfidence
    evidence: list[str] = Field(default_factory=list)


class TechnicalRiskReward(TechnicalAnalysisSchema):
    """Risk/reward ratio for one entry, stop, and target combination."""

    target_label: str = Field(..., min_length=1)
    entry_price: float = Field(..., ge=0)
    stop_loss: float = Field(..., ge=0)
    target_price: float = Field(..., ge=0)
    ratio: float = Field(..., ge=0)


class TechnicalTradingPlan(TechnicalAnalysisSchema):
    """Action-oriented technical plan for setup requests."""

    entry_zone: TechnicalPriceZone
    stop_loss: TechnicalPriceLevel
    target_1: TechnicalPriceLevel
    target_2: TechnicalPriceLevel | None = None
    risk_reward: list[TechnicalRiskReward] = Field(default_factory=list)
    invalidated_if: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_risk_reward(self) -> "TechnicalTradingPlan":
        """Require at least one risk/reward calculation for a trading plan."""
        if not self.risk_reward:
            raise ValueError("risk_reward must contain at least one target calculation")
        return self


class TechnicalBacktestSummary(TechnicalAnalysisSchema):
    """Condensed backtest evidence suitable for analyst synthesis."""

    template_id: BacktestTemplateId
    timeframe: BacktestTimeframe = DEFAULT_BACKTEST_TIMEFRAME
    date_from: date
    date_to: date
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int = Field(..., ge=0)
    profit_factor: float
    notes: list[str] = Field(default_factory=list)
