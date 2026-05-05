"""Domain model for dedicated stock-chat conversations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StockChatConversationStatus(str, Enum):
    """Lifecycle state for a stock-chat conversation."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class StockChatConversation(BaseModel):
    """One stock-chat conversation stored in the dedicated collection."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    id: str | None = Field(default=None, alias="_id")
    user_id: str
    organization_id: str
    title: str
    status: StockChatConversationStatus = StockChatConversationStatus.ACTIVE
    message_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    @field_validator("user_id", "organization_id", mode="before")
    @classmethod
    def require_scope_identifier(cls, value: str) -> str:
        """Require non-blank user and organization identifiers."""
        if not isinstance(value, str):
            raise TypeError("scope identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("scope identifiers must not be blank")
        return normalized

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """Require a non-blank conversation title."""
        if not isinstance(value, str):
            raise TypeError("title must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized
