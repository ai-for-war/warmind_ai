"""Output validation helpers for stock-research agent responses."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CITATION_TOKEN_PATTERN = re.compile(r"\[(S\d+)\]")
THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
SOURCES_SECTION_PATTERN = re.compile(r"^##+\s+Sources\s*$", re.IGNORECASE | re.MULTILINE)
MARKDOWN_REPORT_START_PATTERN = re.compile(
    r"^(#{1,6}\s|\*\*|> |\d+\.\s|[-*]\s)",
    re.MULTILINE,
)
MARKDOWN_SOURCE_LINE_PATTERN = re.compile(
    r"^\s*[-*]\s*\[(S\d+)\]\s+(.+?)\s+\((https?://[^)\s]+)\)\s*$",
    re.MULTILINE,
)


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
    except json.JSONDecodeError:
        return _parse_markdown_output(normalized_payload)

    return StockResearchAgentOutput.model_validate(parsed_payload)


def _parse_markdown_output(payload: str) -> StockResearchAgentOutput:
    """Parse one markdown stock-research report with an optional sources section."""
    normalized_payload = _strip_leading_model_preamble(payload)
    content, sources_block = _split_sources_section(normalized_payload)
    sources = [
        {
            "source_id": source_id,
            "title": title,
            "url": url,
        }
        for source_id, title, url in MARKDOWN_SOURCE_LINE_PATTERN.findall(sources_block)
    ]
    return StockResearchAgentOutput(
        content=content,
        sources=sources,
    )


def _strip_leading_model_preamble(payload: str) -> str:
    """Remove hidden-reasoning blocks and obvious non-report lead-in text."""
    normalized_payload = THINK_BLOCK_PATTERN.sub("", payload).strip()
    report_start = MARKDOWN_REPORT_START_PATTERN.search(normalized_payload)
    if report_start is not None and report_start.start() > 0:
        normalized_payload = normalized_payload[report_start.start() :].strip()
    return normalized_payload


def _split_sources_section(payload: str) -> tuple[str, str]:
    """Split one markdown report into body content and trailing sources block."""
    sources_match = SOURCES_SECTION_PATTERN.search(payload)
    if sources_match is None:
        return payload.strip(), ""
    return (
        payload[: sources_match.start()].strip(),
        payload[sources_match.end() :].strip(),
    )


def _strip_code_fence(value: str) -> str:
    """Extract fenced JSON payloads when the model wraps the final response."""
    lines = value.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return value
