"""Meeting utterance persistence models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MeetingUtteranceMessage(BaseModel):
    """One canonical speaker-grouped message inside a meeting utterance."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    speaker_index: int = Field(..., ge=0)
    speaker_label: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_label(self) -> "MeetingUtteranceMessage":
        """Require the label to match the 0-based speaker index."""
        expected = f"speaker_{self.speaker_index + 1}"
        if self.speaker_label != expected:
            raise ValueError(
                f"speaker_label must match speaker_index as '{expected}'"
            )
        return self


class MeetingUtterance(BaseModel):
    """Durable canonical utterance record for one meeting transcript."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    meeting_id: str
    sequence: int = Field(..., ge=1)
    messages: list[MeetingUtteranceMessage] = Field(..., min_length=1)
    created_at: datetime
