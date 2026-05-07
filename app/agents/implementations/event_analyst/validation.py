"""Output validation helpers for event analyst responses."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CITATION_TOKEN_PATTERN = re.compile(r"\[(S\d+)\]")

EventImpactDirection = Literal["bullish", "bearish", "mixed", "neutral", "unclear"]
EventImpactConfidence = Literal["low", "medium", "high"]
EventImpactHorizon = Literal[
    "immediate",
    "short_term",
    "medium_term",
    "long_term",
    "unclear",
]


class EventAnalystOutputSource(BaseModel):
    """One web source returned by event analyst output."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    source_id: str = Field(
        description="Stable citation identifier used by text references, for example S1."
    )
    url: str = Field(description="Canonical URL for the cited web source.")
    title: str = Field(description="Human-readable title of the cited web source.")

    @field_validator("source_id", "url", "title", mode="before")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """Require non-blank source fields."""
        if not isinstance(value, str):
            raise TypeError("source fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("source fields must not be blank")
        return normalized

    @field_validator("source_id")
    @classmethod
    def validate_source_id_format(cls, value: str) -> str:
        """Require citation IDs to follow the persisted `[Sx]` reference scheme."""
        if not re.fullmatch(r"S\d+", value):
            raise ValueError("source_id must match the S<number> format")
        return value


class EventAnalystEvent(BaseModel):
    """One event or catalyst identified by the event analyst."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    title: str = Field(description="Short name for the event or catalyst.")
    description: str = Field(
        description="Evidence-grounded explanation of what happened and why it matters."
    )
    event_type: str = Field(
        description="Category such as company_news, policy, regulatory, macro, industry, earnings, corporate_action, or risk_event."
    )
    event_date: str | None = Field(
        default=None,
        description="Known event date or publication date in ISO format when available; null when unclear.",
    )
    impact_direction: EventImpactDirection = Field(
        description="Likely directional impact of this specific event on investor expectations for the stock."
    )
    impact_horizon: EventImpactHorizon = Field(
        description="Likely time horizon over which this specific event may matter."
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Source IDs supporting this event, each matching an item in sources.",
    )

    @field_validator("title", "description", "event_type", mode="before")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """Require non-blank event text fields."""
        if not isinstance(value, str):
            raise TypeError("event text fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("event text fields must not be blank")
        return normalized

    @field_validator("event_date", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Normalize optional event date text."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("event_date must be a string when provided")
        normalized = value.strip()
        return normalized or None

    @field_validator("source_ids", mode="before")
    @classmethod
    def normalize_source_ids(cls, values: list[Any] | None) -> list[str]:
        """Normalize optional source ID lists while dropping duplicates."""
        if values is None:
            return []
        if not isinstance(values, list):
            raise TypeError("source_ids must be a list")
        normalized_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                raise TypeError("source_ids must contain strings")
            normalized_value = value.strip()
            if not normalized_value or normalized_value in seen:
                continue
            if not re.fullmatch(r"S\d+", normalized_value):
                raise ValueError("source_ids must match the S<number> format")
            seen.add(normalized_value)
            normalized_values.append(normalized_value)
        return normalized_values


class EventAnalystOutput(BaseModel):
    """Canonical event analyst output contract."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    summary: str = Field(
        description="Concise synthesis of event evidence and likely stock impact; include citation tokens where useful."
    )
    events: list[EventAnalystEvent] = Field(
        default_factory=list,
        description="Concrete event, news, catalyst, policy, macro, regulatory, or industry developments found during research.",
    )
    impact_direction: EventImpactDirection = Field(
        description="Overall direction of the event package for the stock after weighing positive and negative evidence."
    )
    impact_confidence: EventImpactConfidence = Field(
        description="Confidence in the overall event impact assessment based on source quality, recency, and consistency."
    )
    bullish_catalysts: list[str] = Field(
        default_factory=list,
        description="Evidence-grounded upside catalysts or positive developments relevant to the stock.",
    )
    bearish_risks: list[str] = Field(
        default_factory=list,
        description="Evidence-grounded downside risks or negative developments relevant to the stock.",
    )
    uncertainties: list[str] = Field(
        default_factory=list,
        description="Evidence gaps, stale information, unresolved conflicts, missing dates, or scope limitations.",
    )
    sources: list[EventAnalystOutputSource] = Field(
        default_factory=list,
        description="Web sources actually used by the event impact package.",
    )

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

    @field_validator(
        "bullish_catalysts",
        "bearish_risks",
        "uncertainties",
        mode="before",
    )
    @classmethod
    def normalize_text_list(cls, values: list[Any] | None) -> list[str]:
        """Normalize optional text lists while dropping blanks."""
        if values is None:
            return []
        if not isinstance(values, list):
            raise TypeError("value must be a list")
        normalized_values: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise TypeError("list items must be strings")
            normalized_value = value.strip()
            if normalized_value:
                normalized_values.append(normalized_value)
        return normalized_values

    @model_validator(mode="after")
    def validate_sources_and_citations(self) -> "EventAnalystOutput":
        """Enforce unique source IDs and citation-reference integrity."""
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("sources must use unique source_id values")

        available_source_ids = set(source_ids)
        referenced_source_ids = self._referenced_source_ids()
        missing_source_ids = sorted(referenced_source_ids - available_source_ids)
        if missing_source_ids:
            missing_list = ", ".join(missing_source_ids)
            raise ValueError(
                f"output references missing source_id values: {missing_list}"
            )

        return self

    def _referenced_source_ids(self) -> set[str]:
        """Collect source IDs from citation tokens and explicit event source lists."""
        referenced_source_ids = set(CITATION_TOKEN_PATTERN.findall(self.summary))
        for event in self.events:
            referenced_source_ids.update(event.source_ids)
            referenced_source_ids.update(CITATION_TOKEN_PATTERN.findall(event.title))
            referenced_source_ids.update(
                CITATION_TOKEN_PATTERN.findall(event.description)
            )
        for item in [*self.bullish_catalysts, *self.bearish_risks, *self.uncertainties]:
            referenced_source_ids.update(CITATION_TOKEN_PATTERN.findall(item))
        return referenced_source_ids


def parse_event_analyst_output(payload: str | Mapping[str, Any]) -> EventAnalystOutput:
    """Parse and validate one event analyst output payload."""
    if isinstance(payload, Mapping):
        return EventAnalystOutput.model_validate(dict(payload))
    if not isinstance(payload, str):
        raise TypeError("event analyst output must be a JSON string or mapping")

    normalized_payload = payload.strip()
    if not normalized_payload:
        raise ValueError("event analyst output must not be blank")

    if normalized_payload.startswith("```"):
        normalized_payload = _strip_code_fence(normalized_payload)

    return EventAnalystOutput.model_validate(json.loads(normalized_payload))


def _strip_code_fence(value: str) -> str:
    """Extract fenced JSON payloads when the model wraps the final response."""
    lines = value.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return value
