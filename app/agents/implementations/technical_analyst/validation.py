"""Output validation helpers for technical analyst responses."""

from __future__ import annotations

import json
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.schemas.technical_analysis import (
    DEFAULT_TECHNICAL_ANALYSIS_INTERVAL,
    TechnicalAnalysisInterval,
    TechnicalAssessment,
    TechnicalBacktestSummary,
    TechnicalConfidence,
    TechnicalIndicatorSnapshot,
    TechnicalPriceLevel,
    TechnicalRisk,
    TechnicalSignal,
    TechnicalTradingPlan,
    TechnicalUncertainty,
)

TechnicalAnalystMode = Literal["technical_read", "trading_plan"]


class TechnicalAnalystOutput(BaseModel):
    """Canonical synthesis-ready output contract for the technical analyst model."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    mode: TechnicalAnalystMode = Field(
        description=(
            "Output mode selected from the delegated objective. Use 'technical_read' "
            "for chart-state, trend, indicator, support/resistance, momentum, "
            "volatility, or volume-confirmation analysis. Use 'trading_plan' only "
            "when the objective asks for entry zone, stop loss, target, setup, "
            "risk/reward, or strategy/backtest evidence."
        )
    )
    summary: str = Field(
        description=(
            "Concise technical synthesis for the parent stock agent. Summarize the "
            "dominant technical condition, key confirming evidence, key conflicting "
            "evidence, and practical implication. Do not provide the final all-factor "
            "investment recommendation here."
        )
    )
    symbol: str | None = Field(
        default=None,
        description=(
            "Canonical uppercase Vietnam-listed stock symbol being analyzed, such as "
            "'FPT' or 'HPG'. Use null only when the delegated objective does not "
            "identify one clear single-symbol target."
        ),
    )
    interval: TechnicalAnalysisInterval = Field(
        default=DEFAULT_TECHNICAL_ANALYSIS_INTERVAL,
        description=(
            "OHLCV interval used for the technical analysis. Phase one supports only "
            "'1D' daily bars; do not imply intraday, weekly, or monthly execution."
        ),
    )
    confidence: TechnicalConfidence = Field(
        description=(
            "Overall confidence in this technical evidence package: 'low', 'medium', "
            "or 'high'. Base this on data sufficiency, agreement among indicators, "
            "clarity of price structure, and amount of conflicting evidence. This is "
            "not a win probability."
        )
    )
    trend: TechnicalAssessment = Field(
        description=(
            "Trend-state assessment from price structure and trend indicators such "
            "as moving averages, ADX, higher-high/higher-low or lower-high/lower-low "
            "behavior, and price position versus important levels."
        )
    )
    momentum: TechnicalAssessment = Field(
        description=(
            "Momentum-state assessment from indicators such as RSI, MACD, rate of "
            "change, overbought/oversold behavior, and bullish or bearish momentum "
            "divergence when observable."
        )
    )
    volatility: TechnicalAssessment = Field(
        description=(
            "Volatility-state assessment from indicators such as ATR and Bollinger "
            "Bands. Explain whether volatility is expanding, contracting, elevated, "
            "or quiet, and why that matters for setup quality and stop distance."
        )
    )
    volume_confirmation: TechnicalAssessment = Field(
        description=(
            "Assessment of whether volume confirms or contradicts the price move. "
            "Use evidence such as volume versus recent average, accumulation or "
            "distribution behavior, OBV direction, breakout volume, or weak-volume "
            "moves."
        )
    )
    support_levels: list[TechnicalPriceLevel] = Field(
        default_factory=list,
        description=(
            "Important support levels or zones derived from recent swing lows, "
            "historical reaction areas, moving averages, Bollinger levels, or other "
            "technical evidence. Return an empty list when no credible support can "
            "be identified from the available data."
        ),
    )
    resistance_levels: list[TechnicalPriceLevel] = Field(
        default_factory=list,
        description=(
            "Important resistance levels or zones derived from recent swing highs, "
            "historical supply areas, moving averages, Bollinger levels, or other "
            "technical evidence. Return an empty list when no credible resistance "
            "can be identified from the available data."
        ),
    )
    signals: list[TechnicalSignal] = Field(
        default_factory=list,
        description=(
            "Concrete technical signals observed in the evidence, such as moving "
            "average alignment/crossovers, RSI regime shifts, MACD crosses, "
            "breakouts, breakdowns, failed breakouts, divergences, support holds, "
            "or resistance rejections."
        ),
    )
    risks: list[TechnicalRisk] = Field(
        default_factory=list,
        description=(
            "Technical risks that could weaken or invalidate the setup, such as "
            "nearby resistance, weak volume confirmation, extended/overbought price, "
            "trend deterioration, high volatility, poor risk/reward, or conflicting "
            "indicator evidence."
        ),
    )
    uncertainties: list[TechnicalUncertainty] = Field(
        default_factory=list,
        description=(
            "Known evidence gaps, stale or insufficient price history, unavailable "
            "indicators, ambiguous chart structure, conflicting signals, unsupported "
            "interval requests, or other limitations the parent stock agent should "
            "consider during synthesis."
        ),
    )
    indicator_snapshot: TechnicalIndicatorSnapshot | None = Field(
        default=None,
        description=(
            "Structured indicator evidence returned by compute_technical_indicators. "
            "Use null only when the indicator tool was unavailable, failed, or was "
            "not needed for the delegated objective; explain that limitation in "
            "uncertainties when relevant."
        ),
    )
    trading_plan: TechnicalTradingPlan | None = Field(
        default=None,
        description=(
            "Action-oriented technical plan with entry zone, stop loss, targets, "
            "risk/reward, invalidation condition, and rationale. Required when "
            "mode is 'trading_plan'. Must be null when mode is 'technical_read' so "
            "the analyst does not provide unsolicited entry/stop/target levels."
        ),
    )
    backtest_summary: TechnicalBacktestSummary | None = Field(
        default=None,
        description=(
            "Condensed historical backtest evidence returned by run_backtest when "
            "the analyst used a supported deterministic template. Use null when no "
            "backtest was run. Treat this as historical evidence only, not as a "
            "prediction or guarantee."
        ),
    )

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        """Normalize mode identifiers into stable lowercase values."""
        if not isinstance(value, str):
            raise TypeError("mode must be a string")
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("mode must not be blank")
        return normalized

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        """Require non-empty summary text."""
        if not isinstance(value, str):
            raise TypeError("summary must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("summary must not be blank")
        return normalized

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        """Normalize optional symbols into canonical uppercase form."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("symbol must be a string when provided")
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("interval", mode="before")
    @classmethod
    def normalize_interval(cls, value: str | None) -> TechnicalAnalysisInterval:
        """Normalize and constrain phase-one output to daily bars."""
        if value is None:
            return DEFAULT_TECHNICAL_ANALYSIS_INTERVAL
        if not isinstance(value, str):
            raise TypeError("interval must be a string")
        normalized = value.strip().upper()
        return normalized or DEFAULT_TECHNICAL_ANALYSIS_INTERVAL  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "TechnicalAnalystOutput":
        """Keep trading-plan fields exclusive to explicit plan mode."""
        if self.mode == "technical_read" and self.trading_plan is not None:
            raise ValueError("technical_read output must not include trading_plan")
        if self.mode == "trading_plan" and self.trading_plan is None:
            raise ValueError("trading_plan output requires trading_plan")
        return self


def parse_technical_analyst_output(
    payload: str | Mapping[str, Any],
) -> TechnicalAnalystOutput:
    """Parse and validate one technical analyst output payload."""
    if isinstance(payload, Mapping):
        return TechnicalAnalystOutput.model_validate(dict(payload))
    if not isinstance(payload, str):
        raise TypeError("technical analyst output must be a JSON string or mapping")

    normalized_payload = payload.strip()
    if not normalized_payload:
        raise ValueError("technical analyst output must not be blank")

    if normalized_payload.startswith("```"):
        normalized_payload = _strip_code_fence(normalized_payload)

    return TechnicalAnalystOutput.model_validate(json.loads(normalized_payload))


def _strip_code_fence(value: str) -> str:
    """Extract fenced JSON payloads when the model wraps the final response."""
    lines = value.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return value
