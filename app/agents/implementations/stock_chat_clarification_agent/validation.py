"""Structured output validation for stock-chat clarification decisions."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CLARIFICATION_OPTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class StockChatClarificationOption(BaseModel):
    """One user-facing clarification option."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., description="Stable user-facing option id.")
    label: str = Field(..., description="Short option label displayed to the user.")
    description: str = Field(
        ...,
        description="Natural-language answer the client can send back if selected.",
    )

    @field_validator("id", "label", "description", mode="before")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        """Require non-blank option fields."""
        if not isinstance(value, str):
            raise TypeError("clarification option fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("clarification option fields must not be blank")
        return normalized

    @field_validator("id")
    @classmethod
    def validate_option_id(cls, value: str) -> str:
        """Keep option IDs stable without carrying backend state patches."""
        normalized = value.lower()
        if not CLARIFICATION_OPTION_ID_PATTERN.fullmatch(normalized):
            raise ValueError(
                "clarification option id must match "
                "^[a-z][a-z0-9_-]{1,63}$"
            )
        return normalized


class StockChatClarificationPayload(BaseModel):
    """Clarification prompt returned when the transcript is missing context."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(..., min_length=1, max_length=1000)
    options: list[StockChatClarificationOption] = Field(
        ...,
        min_length=2,
        max_length=4,
    )

    @field_validator("question", mode="before")
    @classmethod
    def require_question(cls, value: str) -> str:
        """Require a non-blank clarification question."""
        if not isinstance(value, str):
            raise TypeError("clarification question must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("clarification question must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_unique_option_ids(self) -> "StockChatClarificationPayload":
        """Require each clarification option id to be unique."""
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("clarification option ids must be unique")
        return self


class StockChatClarificationResult(BaseModel):
    """Canonical clarification-agent output contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal["clarification_required", "continue"]
    clarification: StockChatClarificationPayload | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "StockChatClarificationResult":
        """Enforce one of the two allowed clarification decisions."""
        if self.status == "clarification_required" and self.clarification is None:
            raise ValueError(
                "clarification is required when status is clarification_required"
            )
        if self.status == "continue" and self.clarification is not None:
            raise ValueError("clarification must be omitted when status is continue")
        return self


def parse_stock_chat_clarification_result(
    payload: str | Mapping[str, Any] | StockChatClarificationResult,
) -> StockChatClarificationResult:
    """Parse and validate one stock-chat clarification-agent output payload."""
    if isinstance(payload, StockChatClarificationResult):
        return payload
    if isinstance(payload, Mapping):
        return StockChatClarificationResult.model_validate(dict(payload))
    if not isinstance(payload, str):
        raise TypeError(
            "stock-chat clarification result must be a JSON string or mapping"
        )

    normalized_payload = payload.strip()
    if not normalized_payload:
        raise ValueError("stock-chat clarification result must not be blank")
    if normalized_payload.startswith("```"):
        normalized_payload = _strip_code_fence(normalized_payload)

    parsed_payload = json.loads(normalized_payload)
    return StockChatClarificationResult.model_validate(parsed_payload)


def _strip_code_fence(value: str) -> str:
    """Extract a fenced JSON payload when a model wraps the response."""
    lines = value.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return value
