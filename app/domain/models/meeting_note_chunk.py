"""Meeting note chunk persistence models."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _normalize_non_empty_text_list(
    value: Sequence[str] | None,
    *,
    field_name: str,
) -> list[str]:
    """Normalize a list of persisted note strings."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence of strings")

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must contain only strings")
        stripped = item.strip()
        if not stripped:
            raise ValueError(f"{field_name} entries must not be blank")
        normalized.append(stripped)
    return normalized


class MeetingNoteActionItem(BaseModel):
    """One structured action item extracted from a meeting note chunk."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=1)
    owner_text: str | None = None
    due_text: str | None = None

    @field_validator("owner_text", "due_text", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Collapse blank optional values to null for stable persistence."""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class MeetingNoteChunk(BaseModel):
    """Durable structured note chunk covering one meeting utterance range."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    id: str = Field(alias="_id")
    meeting_id: str
    from_sequence: int = Field(..., ge=1)
    to_sequence: int = Field(..., ge=1)
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[MeetingNoteActionItem] = Field(default_factory=list)
    created_at: datetime

    @field_validator("key_points", mode="before")
    @classmethod
    def normalize_key_points(cls, value: Sequence[str] | None) -> list[str]:
        """Persist key points as a list of non-blank strings."""
        return _normalize_non_empty_text_list(value, field_name="key_points")

    @field_validator("decisions", mode="before")
    @classmethod
    def normalize_decisions(cls, value: Sequence[str] | None) -> list[str]:
        """Persist decisions as a list of non-blank strings."""
        return _normalize_non_empty_text_list(value, field_name="decisions")

    @model_validator(mode="after")
    def validate_range_and_content(self) -> "MeetingNoteChunk":
        """Require a valid sequence range and at least one persisted note item."""
        if self.from_sequence > self.to_sequence:
            raise ValueError("from_sequence must be less than or equal to to_sequence")
        if not self.key_points and not self.decisions and not self.action_items:
            raise ValueError(
                "meeting note chunk must include at least one note item"
            )
        return self
