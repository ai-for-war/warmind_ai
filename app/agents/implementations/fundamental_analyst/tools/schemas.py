"""Input schemas for fundamental analyst tools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoadCompanyProfileInput(BaseModel):
    """Arguments for loading VCI company profile evidence."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    symbol: str = Field(
        description="Vietnam-listed stock symbol to load company overview for."
    )


class LoadFinancialReportInput(BaseModel):
    """Arguments shared by KBS financial report tools."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    symbol: str = Field(
        description="Vietnam-listed stock symbol to load financial evidence for."
    )
    period: str = Field(
        default="quarter",
        description="Financial report period. Supported values are quarter and year.",
    )
