"""Output validation helpers for stock-research agent responses."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CITATION_TOKEN_PATTERN = re.compile(r"\[(S\d+)\]")


class StockResearchAgentOutputSource(BaseModel):
    """One persisted web source returned by stock research agent output."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    source_id: str
    url: str
    title: str

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


class StockResearchAgentOutput(BaseModel):
    """Canonical stock research agent output contract."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    content: str
    sources: list[StockResearchAgentOutputSource] = Field(default_factory=list)

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        """Require non-empty markdown content."""
        if not isinstance(value, str):
            raise TypeError("content must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_sources_and_citations(self) -> "StockResearchAgentOutput":
        """Enforce unique source IDs and citation-reference integrity."""
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("sources must use unique source_id values")

        cited_source_ids = set(CITATION_TOKEN_PATTERN.findall(self.content))
        available_source_ids = set(source_ids)
        missing_source_ids = sorted(cited_source_ids - available_source_ids)
        if missing_source_ids:
            missing_list = ", ".join(missing_source_ids)
            raise ValueError(
                f"content cites missing source_id values: {missing_list}"
            )

        return self


def parse_stock_research_output(payload: str | Mapping[str, Any]) -> StockResearchAgentOutput:
    """Parse and validate one stock research agent output payload."""
    if isinstance(payload, Mapping):
        return StockResearchAgentOutput.model_validate(dict(payload))
    if not isinstance(payload, str):
        raise TypeError("stock research output must be a JSON string or mapping")

    normalized_payload = payload.strip()
    if not normalized_payload:
        raise ValueError("stock research output must not be blank")

    if normalized_payload.startswith("```"):
        normalized_payload = _strip_code_fence(normalized_payload)

    try:
        parsed_payload = json.loads(normalized_payload)
    except json.JSONDecodeError as exc:
        raise ValueError("stock research output must be valid JSON") from exc

    return StockResearchAgentOutput.model_validate(parsed_payload)


def _strip_code_fence(value: str) -> str:
    """Extract fenced JSON payloads when the model wraps the final response."""
    lines = value.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return value
