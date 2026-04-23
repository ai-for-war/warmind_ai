"""Schemas for notification request and response payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_NOTIFICATION_PAGE_SIZE = 20
MAX_NOTIFICATION_LIST_LIMIT = 100


class NotificationSchemaBase(BaseModel):
    """Base schema defaults for notification API payloads."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class NotificationListQuery(NotificationSchemaBase):
    """Query parameters for scoped notification inbox reads."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default=DEFAULT_NOTIFICATION_PAGE_SIZE,
        ge=1,
        le=MAX_NOTIFICATION_LIST_LIMIT,
    )


class NotificationOwnership(NotificationSchemaBase):
    """Ownership scope attached to notification resources."""

    user_id: str = Field(..., min_length=1)
    organization_id: str = Field(..., min_length=1)


class NotificationSummary(NotificationOwnership):
    """Frontend-facing summary for one notification inbox item."""

    id: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    target_type: str = Field(..., min_length=1)
    target_id: str = Field(..., min_length=1)
    link: str | None = None
    actor_id: str | None = None
    metadata: dict[str, Any] | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime

    @field_validator("type", "title", "body", "target_type", "target_id", mode="before")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        """Require non-blank summary text for core notification fields."""
        if not isinstance(value, str):
            raise TypeError("notification summary fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("notification summary fields must not be blank")
        return normalized

    @field_validator("link", "actor_id", mode="before")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        """Collapse blank optional notification text fields to null."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("optional notification summary fields must be strings or None")
        normalized = value.strip()
        return normalized or None


class NotificationListResponse(NotificationSchemaBase):
    """Response returned by the notification inbox list endpoint."""

    items: list[NotificationSummary] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=MAX_NOTIFICATION_LIST_LIMIT)


class NotificationUnreadCountResponse(NotificationSchemaBase):
    """Response returned by the unread-count endpoint."""

    unread_count: int = Field(..., ge=0)


class NotificationMarkReadResponse(NotificationSchemaBase):
    """Response returned after marking one notification as read."""

    id: str = Field(..., min_length=1)
    is_read: bool = True
    read_at: datetime


class NotificationMarkAllReadResponse(NotificationSchemaBase):
    """Response returned after marking all scoped notifications as read."""

    updated_count: int = Field(..., ge=0)
    marked_all_read: bool = True
    read_at: datetime
