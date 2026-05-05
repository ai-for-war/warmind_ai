"""Domain model for dedicated stock-chat transcript messages."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StockChatMessageRole(str, Enum):
    """Persisted speaker role for stock-chat transcripts."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class StockChatMessage(BaseModel):
    """One stock-chat transcript message stored in the dedicated collection."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    id: str | None = Field(default=None, alias="_id")
    conversation_id: str
    user_id: str
    organization_id: str
    role: StockChatMessageRole
    content: str
    metadata: dict[str, Any] | None = None
    created_at: datetime
    deleted_at: datetime | None = None

    @field_validator("conversation_id", "user_id", "organization_id", mode="before")
    @classmethod
    def require_identifier(cls, value: str) -> str:
        """Require non-blank ownership identifiers."""
        if not isinstance(value, str):
            raise TypeError("identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifiers must not be blank")
        return normalized

    @field_validator("content", mode="before")
    @classmethod
    def require_content(cls, value: str) -> str:
        """Require non-blank transcript content."""
        if not isinstance(value, str):
            raise TypeError("content must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized
