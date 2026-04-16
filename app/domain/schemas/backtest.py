"""Schemas for internal stock backtest request and response payloads."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.domain.schemas.stock import StockSchemaBase

BacktestTimeframe = Literal["1D"]
BacktestTemplateId = Literal["buy_and_hold", "sma_crossover"]
BacktestExposure = Literal["long_only"]
BacktestPositionSizing = Literal["all_in"]
BacktestExecutionModel = Literal["next_open"]

DEFAULT_BACKTEST_TIMEFRAME: BacktestTimeframe = "1D"
DEFAULT_BACKTEST_TEMPLATE_ID: BacktestTemplateId = "buy_and_hold"
DEFAULT_BACKTEST_EXPOSURE: BacktestExposure = "long_only"
DEFAULT_BACKTEST_POSITION_SIZING: BacktestPositionSizing = "all_in"
DEFAULT_BACKTEST_EXECUTION_MODEL: BacktestExecutionModel = "next_open"
DEFAULT_BACKTEST_INITIAL_CAPITAL = 100_000_000


class BacktestTemplateParamsBase(StockSchemaBase):
    """Base schema for one backtest template's parameters."""


class BuyAndHoldTemplateParams(BacktestTemplateParamsBase):
    """Template parameters for the buy-and-hold strategy."""


class SmaCrossoverTemplateParams(BacktestTemplateParamsBase):
    """Template parameters for the SMA crossover strategy."""

    fast_window: int = Field(..., ge=1)
    slow_window: int = Field(..., ge=1)

    @model_validator(mode="after")
    def validate_window_order(self) -> "SmaCrossoverTemplateParams":
        """Require the fast moving-average window to stay below the slow one."""
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be less than slow_window")
        return self


BacktestTemplateParams = BuyAndHoldTemplateParams | SmaCrossoverTemplateParams


class BacktestRunRequest(StockSchemaBase):
    """Validated request contract for one internal backtest run."""

    symbol: str = Field(..., min_length=1)
    timeframe: BacktestTimeframe = DEFAULT_BACKTEST_TIMEFRAME
    date_from: date
    date_to: date
    direction: BacktestExposure = DEFAULT_BACKTEST_EXPOSURE
    position_sizing: BacktestPositionSizing = DEFAULT_BACKTEST_POSITION_SIZING
    execution_model: BacktestExecutionModel = DEFAULT_BACKTEST_EXECUTION_MODEL
    template_id: BacktestTemplateId = DEFAULT_BACKTEST_TEMPLATE_ID
    template_params: BacktestTemplateParams = Field(
        default_factory=BuyAndHoldTemplateParams
    )
    initial_capital: int = Field(default=DEFAULT_BACKTEST_INITIAL_CAPITAL, gt=0)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize request symbols to uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("timeframe", mode="before")
    @classmethod
    def normalize_timeframe(cls, value: str | None) -> BacktestTimeframe:
        """Normalize timeframe text into the canonical daily value."""
        if value is None:
            return DEFAULT_BACKTEST_TIMEFRAME
        if not isinstance(value, str):
            raise TypeError("timeframe must be a string")
        normalized = value.strip().upper()
        if not normalized:
            return DEFAULT_BACKTEST_TIMEFRAME
        return normalized  # type: ignore[return-value]

    @field_validator(
        "direction",
        "position_sizing",
        "execution_model",
        "template_id",
        mode="before",
    )
    @classmethod
    def normalize_lowercase_literal(cls, value: str | None) -> str:
        """Normalize literal text fields to lowercase stable values."""
        if value is None:
            return ""
        if not isinstance(value, str):
            raise TypeError("literal fields must be strings")
        return value.strip().lower()

    @field_validator("template_params", mode="before")
    @classmethod
    def normalize_template_params(cls, value: object) -> object:
        """Treat omitted template params as an empty parameter object."""
        if value is None or value == "":
            return {}
        return value

    @model_validator(mode="after")
    def validate_request_scope(self) -> "BacktestRunRequest":
        """Validate the v1 request contract and template-to-params mapping."""
        if self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")

        if self.template_id == "buy_and_hold":
            if not isinstance(self.template_params, BuyAndHoldTemplateParams):
                raise ValueError("buy_and_hold does not accept template parameters")
            return self

        if not isinstance(self.template_params, SmaCrossoverTemplateParams):
            raise ValueError(
                "sma_crossover requires template_params with fast_window and slow_window"
            )
        return self


class BacktestSummaryMetrics(StockSchemaBase):
    """Run-level summary metadata for one backtest result."""

    symbol: str = Field(..., min_length=1)
    template_id: BacktestTemplateId
    timeframe: BacktestTimeframe
    date_from: date
    date_to: date
    initial_capital: int = Field(..., ge=0)
    ending_equity: float = Field(..., ge=0)
    total_trades: int = Field(..., ge=0)


class BacktestPerformanceMetrics(StockSchemaBase):
    """Derived performance indicators for one backtest run."""

    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    avg_win_pct: float
    avg_loss_pct: float
    expectancy: float


class BacktestTradeLogEntry(StockSchemaBase):
    """One completed trade record emitted by a backtest run."""

    entry_time: str = Field(..., min_length=1)
    entry_price: float = Field(..., ge=0)
    exit_time: str = Field(..., min_length=1)
    exit_price: float = Field(..., ge=0)
    shares: int = Field(..., ge=0)
    invested_capital: float = Field(..., ge=0)
    pnl: float
    pnl_pct: float
    exit_reason: str = Field(..., min_length=1)


class BacktestBar(StockSchemaBase):
    """One canonical daily OHLCV bar used for backtest execution."""

    time: str = Field(..., min_length=1)
    open: float = Field(..., ge=0)
    high: float = Field(..., ge=0)
    low: float = Field(..., ge=0)
    close: float = Field(..., ge=0)
    volume: float = Field(..., ge=0)


class BacktestEquityCurvePoint(StockSchemaBase):
    """One time-ordered equity snapshot from a backtest run."""

    time: str = Field(..., min_length=1)
    cash: float = Field(..., ge=0)
    market_value: float = Field(..., ge=0)
    equity: float = Field(..., ge=0)
    drawdown_pct: float
    position_size: int = Field(..., ge=0)


class BacktestRunResponse(StockSchemaBase):
    """Structured result contract for one completed backtest run."""

    summary_metrics: BacktestSummaryMetrics
    performance_metrics: BacktestPerformanceMetrics
    trade_log: list[BacktestTradeLogEntry]
    equity_curve: list[BacktestEquityCurvePoint]
