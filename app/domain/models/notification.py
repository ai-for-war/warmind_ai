"""Durable in-app notification persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationModelBase(BaseModel):
    """Common persistence model settings for notification documents."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class Notification(NotificationModelBase):
    """One persisted in-app notification inbox record."""

    id: str | None = Field(default=None, alias="_id")
    user_id: str
    organization_id: str
    type: str
    title: str
    body: str
    target_type: str
    target_id: str
    link: str | None = None
    actor_id: str | None = None
    dedupe_key: str | None = None
    metadata: dict[str, Any] | None = None
    is_read: bool = False
    read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "user_id",
        "organization_id",
        "type",
        "title",
        "body",
        "target_type",
        "target_id",
        mode="before",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        """Require core persisted notification fields to be non-blank strings."""
        if not isinstance(value, str):
            raise TypeError("notification fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("notification fields must not be blank")
        return normalized

    @field_validator("link", "actor_id", "dedupe_key", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Collapse blank optional text fields to null for stable persistence."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("optional notification fields must be strings or None")
        normalized = value.strip()
        return normalized or None
