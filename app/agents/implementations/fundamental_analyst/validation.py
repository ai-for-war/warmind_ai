"""Output validation helpers for fundamental analyst responses."""

from __future__ import annotations

import json
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FundamentalAnalysisPeriod = Literal["quarter", "year"]
FundamentalConfidence = Literal["low", "medium", "high"]
FundamentalCellValue = int | float | str | bool | None


class FundamentalEvidenceRow(BaseModel):
    """One raw provider row or profile field supporting an evidence section."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    item: str = Field(
        description="Raw provider item name or canonical profile field name."
    )
    report_type: str | None = Field(
        default=None,
        description="KBS report type when the row comes from a financial report.",
    )
    periods: list[str] = Field(
        default_factory=list,
        description="Provider period labels included in this row.",
    )
    values: dict[str, FundamentalCellValue] = Field(
        default_factory=dict,
        description="Values keyed by provider period label or profile field key.",
    )

    @field_validator("item", mode="before")
    @classmethod
    def normalize_item(cls, value: str) -> str:
        """Require non-empty row item text."""
        return _require_text(value, "item")

    @field_validator("report_type", mode="before")
    @classmethod
    def normalize_optional_report_type(cls, value: str | None) -> str | None:
        """Normalize optional report type text."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("report_type must be a string when provided")
        normalized = value.strip()
        return normalized or None

    @field_validator("periods", mode="before")
    @classmethod
    def normalize_periods(cls, values: list[Any] | None) -> list[str]:
        """Normalize provider period labels while dropping blanks and duplicates."""
        return _normalize_text_list(values)


class FundamentalEvidenceSection(BaseModel):
    """Shared section shape for fundamental evidence and interpretation."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    assessment: str = Field(
        description="Concise section-level assessment based on available evidence."
    )
    evidence_rows: list[FundamentalEvidenceRow] = Field(
        default_factory=list,
        description="Selected raw evidence rows supporting this assessment.",
    )
    interpretation: str = Field(
        description="Explanation of what the evidence suggests and what it does not prove."
    )
    risks: list[str] = Field(
        default_factory=list,
        description="Section-specific risks or negative readings.",
    )
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Section-specific missing evidence, stale data, or limitations.",
    )

    @field_validator("assessment", "interpretation", mode="before")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """Require non-empty section text."""
        return _require_text(value, "section text")

    @field_validator("risks", "data_gaps", mode="before")
    @classmethod
    def normalize_text_list(cls, values: list[Any] | None) -> list[str]:
        """Normalize optional text lists while dropping blanks."""
        return _normalize_text_list(values)

    @model_validator(mode="after")
    def validate_evidence_or_gap(self) -> "FundamentalEvidenceSection":
        """Require either row support or explicit gaps for each section."""
        if not self.evidence_rows and not self.data_gaps:
            raise ValueError("section requires evidence_rows or data_gaps")
        return self


class FundamentalAnalystOutput(BaseModel):
    """Canonical synthesis-ready output contract for the fundamental analyst."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    symbol: str = Field(
        description="Canonical uppercase Vietnam-listed stock symbol being analyzed."
    )
    period: FundamentalAnalysisPeriod = Field(
        default="quarter",
        description="Financial evidence period used by the analyst: quarter or year.",
    )
    summary: str = Field(
        description=(
            "Concise fundamental synthesis for the parent stock agent. Do not provide "
            "the final all-factor investment recommendation here."
        )
    )
    confidence: FundamentalConfidence = Field(
        description=(
            "Overall confidence in this fundamental evidence package based on data "
            "coverage, recency, consistency, and data gaps."
        )
    )
    business_profile: FundamentalEvidenceSection = Field(
        description="Business profile evidence from VCI company overview."
    )
    growth: FundamentalEvidenceSection = Field(
        description="Revenue, profit, EPS, or reported growth evidence from KBS rows."
    )
    profitability: FundamentalEvidenceSection = Field(
        description="Reported profitability evidence such as margins, ROE, ROA, or profit rows."
    )
    financial_health: FundamentalEvidenceSection = Field(
        description="Balance-sheet, leverage, liquidity, asset, liability, and equity evidence."
    )
    cash_flow_quality: FundamentalEvidenceSection = Field(
        description="Operating, investing, financing cash-flow evidence and profit-vs-cash context."
    )
    valuation_ratios: FundamentalEvidenceSection = Field(
        description="Reported valuation-ratio evidence such as P/E, P/B, EPS, or book-value rows."
    )
    bullish_fundamental_points: list[str] = Field(
        default_factory=list,
        description="Evidence-grounded positive fundamental points for parent synthesis.",
    )
    bearish_fundamental_risks: list[str] = Field(
        default_factory=list,
        description="Evidence-grounded negative fundamental risks for parent synthesis.",
    )
    uncertainties: list[str] = Field(
        default_factory=list,
        description="Interpretation uncertainties, conflicts, and scope limitations.",
    )
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Concrete data gaps across tools and evidence sections.",
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize symbols into canonical uppercase form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("period", mode="before")
    @classmethod
    def normalize_period(cls, value: str | None) -> FundamentalAnalysisPeriod:
        """Normalize omitted or blank periods to quarterly evidence."""
        if value is None:
            return "quarter"
        if not isinstance(value, str):
            raise TypeError("period must be a string")
        normalized = value.strip().lower()
        return normalized or "quarter"  # type: ignore[return-value]

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        """Require non-empty summary text."""
        return _require_text(value, "summary")

    @field_validator(
        "bullish_fundamental_points",
        "bearish_fundamental_risks",
        "uncertainties",
        "data_gaps",
        mode="before",
    )
    @classmethod
    def normalize_text_list(cls, values: list[Any] | None) -> list[str]:
        """Normalize optional text lists while dropping blanks."""
        return _normalize_text_list(values)


def parse_fundamental_analyst_output(
    payload: str | Mapping[str, Any],
) -> FundamentalAnalystOutput:
    """Parse and validate one fundamental analyst output payload."""
    if isinstance(payload, Mapping):
        return FundamentalAnalystOutput.model_validate(dict(payload))
    if not isinstance(payload, str):
        raise TypeError("fundamental analyst output must be a JSON string or mapping")

    normalized_payload = payload.strip()
    if not normalized_payload:
        raise ValueError("fundamental analyst output must not be blank")

    if normalized_payload.startswith("```"):
        normalized_payload = _strip_code_fence(normalized_payload)

    return FundamentalAnalystOutput.model_validate(json.loads(normalized_payload))


def _strip_code_fence(value: str) -> str:
    """Extract fenced JSON payloads when the model wraps the final response."""
    lines = value.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return value


def _require_text(value: str, field_name: str) -> str:
    """Normalize one required non-blank text value."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_text_list(values: list[Any] | None) -> list[str]:
    """Normalize optional text lists while dropping blanks and duplicates."""
    if values is None:
        return []
    if not isinstance(values, list):
        raise TypeError("value must be a list")
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError("list items must be strings")
        normalized_value = value.strip()
        if not normalized_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values
