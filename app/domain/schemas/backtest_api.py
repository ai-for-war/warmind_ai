"""Public API schemas for the dedicated backtest domain."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.schemas.backtest import (
    BacktestExecutionModel,
    BacktestExposure,
    BacktestPositionSizing,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestTemplateId,
    BacktestTemplateParams,
    BacktestTimeframe,
    BuyAndHoldTemplateParams,
    DEFAULT_BACKTEST_EXECUTION_MODEL,
    DEFAULT_BACKTEST_EXPOSURE,
    DEFAULT_BACKTEST_INITIAL_CAPITAL,
    DEFAULT_BACKTEST_POSITION_SIZING,
    DEFAULT_BACKTEST_TIMEFRAME,
    SmaCrossoverTemplateParams,
)

BacktestTemplateParameterType = Literal["integer"]


class BacktestApiSchema(BaseModel):
    """Base schema defaults for FE-facing backtest API payloads."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BacktestApiRunRequest(BacktestApiSchema):
    """FE-facing request contract for one synchronous backtest run."""

    symbol: str = Field(..., min_length=1)
    date_from: date
    date_to: date
    template_id: BacktestTemplateId
    template_params: BacktestTemplateParams = Field(
        default_factory=BuyAndHoldTemplateParams
    )
    initial_capital: int = Field(default=DEFAULT_BACKTEST_INITIAL_CAPITAL, gt=0)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize FE-supplied stock symbols to uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

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
    def validate_template_scope(self) -> "BacktestApiRunRequest":
        """Validate public run scope and template-param compatibility."""
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

    def to_internal_request(self) -> BacktestRunRequest:
        """Map the FE-facing request into the internal backtest request."""
        return BacktestRunRequest(
            symbol=self.symbol,
            date_from=self.date_from,
            date_to=self.date_to,
            template_id=self.template_id,
            template_params=self.template_params,
            initial_capital=self.initial_capital,
        )


class BacktestApiTemplateParameterResponse(BacktestApiSchema):
    """One FE-facing parameter definition for a supported backtest template."""

    name: str = Field(..., min_length=1)
    type: BacktestTemplateParameterType
    required: bool
    default: int | None = None
    min: int | None = Field(default=None, ge=0)
    description: str | None = None


class BacktestApiTemplateResponse(BacktestApiSchema):
    """FE-facing metadata for one supported backtest template."""

    template_id: BacktestTemplateId
    display_name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    parameters: list[BacktestApiTemplateParameterResponse] = Field(default_factory=list)


class BacktestApiTemplateListResponse(BacktestApiSchema):
    """Response schema for the public backtest template catalog."""

    items: list[BacktestApiTemplateResponse]


class BacktestApiRunAssumptionsResponse(BacktestApiSchema):
    """Response schema describing the backend-applied execution assumptions."""

    timeframe: BacktestTimeframe = DEFAULT_BACKTEST_TIMEFRAME
    direction: BacktestExposure = DEFAULT_BACKTEST_EXPOSURE
    position_sizing: BacktestPositionSizing = DEFAULT_BACKTEST_POSITION_SIZING
    execution_model: BacktestExecutionModel = DEFAULT_BACKTEST_EXECUTION_MODEL
    initial_capital: int = Field(..., gt=0)

    @classmethod
    def from_run_request(
        cls,
        request: BacktestRunRequest | BacktestApiRunRequest,
    ) -> "BacktestApiRunAssumptionsResponse":
        """Build the FE-facing assumptions block from one run request."""
        return cls(
            timeframe=request.timeframe if hasattr(request, "timeframe") else "1D",
            direction=request.direction if hasattr(request, "direction") else "long_only",
            position_sizing=(
                request.position_sizing
                if hasattr(request, "position_sizing")
                else "all_in"
            ),
            execution_model=(
                request.execution_model
                if hasattr(request, "execution_model")
                else "next_open"
            ),
            initial_capital=request.initial_capital,
        )


class BacktestApiRunResponse(BacktestApiSchema):
    """FE-facing response for one completed synchronous backtest run."""

    result: BacktestRunResponse
    assumptions: BacktestApiRunAssumptionsResponse
