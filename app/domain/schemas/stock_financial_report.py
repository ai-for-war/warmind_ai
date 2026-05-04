"""Schemas for KBS stock financial report request and response payloads."""

from __future__ import annotations

from enum import Enum
from typing import Literal, TypeAlias

from pydantic import ConfigDict, Field, field_validator

from app.domain.schemas.stock import StockSchemaBase

StockFinancialReportSource = Literal["KBS"]
StockFinancialReportCellValue: TypeAlias = int | float | str | None


class StockFinancialReportType(str, Enum):
    """Supported KBS financial report types."""

    INCOME_STATEMENT = "income-statement"
    BALANCE_SHEET = "balance-sheet"
    CASH_FLOW = "cash-flow"
    RATIO = "ratio"


class StockFinancialReportPeriod(str, Enum):
    """Supported KBS financial report period granularities."""

    QUARTER = "quarter"
    YEAR = "year"


DEFAULT_STOCK_FINANCIAL_REPORT_PERIOD = StockFinancialReportPeriod.QUARTER


class StockFinancialReportSchemaBase(StockSchemaBase):
    """Base schema for stock financial report transport payloads."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        use_enum_values=True,
    )


class StockFinancialReportQuery(StockFinancialReportSchemaBase):
    """Query parameters for one stock financial report read."""

    period: StockFinancialReportPeriod = Field(
        default=DEFAULT_STOCK_FINANCIAL_REPORT_PERIOD,
        validate_default=True,
    )

    @field_validator("period", mode="before")
    @classmethod
    def normalize_period(cls, value: str | StockFinancialReportPeriod | None) -> str:
        """Normalize omitted or blank period query values to the default period."""
        if value is None:
            return DEFAULT_STOCK_FINANCIAL_REPORT_PERIOD.value
        if isinstance(value, StockFinancialReportPeriod):
            return value.value
        if not isinstance(value, str):
            raise TypeError("period must be a string")
        normalized = value.strip().lower()
        return normalized or DEFAULT_STOCK_FINANCIAL_REPORT_PERIOD.value


class StockFinancialReportItem(StockFinancialReportSchemaBase):
    """One financial statement row with period-keyed values."""

    item: str = Field(..., min_length=1)
    item_id: str | int | None = None
    values: dict[str, StockFinancialReportCellValue] = Field(default_factory=dict)


class StockFinancialReportResponse(StockFinancialReportSchemaBase):
    """Response envelope for one KBS-backed financial report read."""

    symbol: str = Field(..., min_length=1)
    source: StockFinancialReportSource = "KBS"
    report_type: StockFinancialReportType
    period: StockFinancialReportPeriod = Field(validate_default=True)
    periods: list[str] = Field(default_factory=list)
    cache_hit: bool = False
    items: list[StockFinancialReportItem]

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist response symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("report_type", mode="before")
    @classmethod
    def normalize_report_type(
        cls,
        value: str | StockFinancialReportType,
    ) -> str:
        """Normalize report type text before enum validation."""
        if isinstance(value, StockFinancialReportType):
            return value.value
        if not isinstance(value, str):
            raise TypeError("report_type must be a string")
        return value.strip().lower()

    @field_validator("period", mode="before")
    @classmethod
    def normalize_period(cls, value: str | StockFinancialReportPeriod) -> str:
        """Normalize response period text before enum validation."""
        if isinstance(value, StockFinancialReportPeriod):
            return value.value
        if not isinstance(value, str):
            raise TypeError("period must be a string")
        return value.strip().lower()
