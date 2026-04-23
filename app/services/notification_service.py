"""Service layer for in-app notification reads, writes, and realtime emit."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.common.event_socket import NotificationEvents
from app.common.exceptions import (
    NotificationNotFoundError,
    NotificationOwnershipError,
)
from app.domain.models.notification import Notification
from app.domain.models.user import User
from app.domain.schemas.notification import (
    NotificationListResponse,
    NotificationMarkAllReadResponse,
    NotificationMarkReadResponse,
    NotificationSummary,
    NotificationUnreadCountResponse,
)
from app.repo.notification_repo import NotificationRepository


class NotificationService:
    """Coordinate notification persistence, dedupe, reads, and realtime emit."""

    def __init__(self, *, notification_repo: NotificationRepository) -> None:
        self.notification_repo = notification_repo

    async def create_notification(
        self,
        *,
        user_id: str,
        organization_id: str,
        type: str,
        title: str,
        body: str,
        target_type: str,
        target_id: str,
        link: str | None = None,
        actor_id: str | None = None,
        dedupe_key: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> NotificationSummary:
        """Persist one notification and emit a realtime created event."""
        normalized_type = self._require_non_blank_text(type, field_name="type")
        normalized_title = self._require_non_blank_text(title, field_name="title")
        normalized_body = self._require_non_blank_text(body, field_name="body")
        normalized_target_type = self._require_non_blank_text(
            target_type,
            field_name="target_type",
        )
        normalized_target_id = self._require_non_blank_text(
            target_id,
            field_name="target_id",
        )
        normalized_link = self._normalize_optional_text(link)
        normalized_actor_id = self._normalize_optional_text(actor_id)
        normalized_dedupe_key = self._normalize_optional_text(dedupe_key)
        normalized_metadata = self._normalize_metadata(metadata)

        if normalized_dedupe_key is not None:
            existing = await self.notification_repo.find_by_dedupe_key(
                user_id=user_id,
                organization_id=organization_id,
                dedupe_key=normalized_dedupe_key,
            )
            if existing is not None:
                return self._to_summary(existing)

        notification = await self.notification_repo.create(
            user_id=user_id,
            organization_id=organization_id,
            type=normalized_type,
            title=normalized_title,
            body=normalized_body,
            target_type=normalized_target_type,
            target_id=normalized_target_id,
            link=normalized_link,
            actor_id=normalized_actor_id,
            dedupe_key=normalized_dedupe_key,
            metadata=normalized_metadata,
        )
        await self._emit_created_event(notification)
        return self._to_summary(notification)

    async def list_notifications(
        self,
        *,
        current_user: User,
        organization_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> NotificationListResponse:
        """List one caller's notifications in one organization scope."""
        notifications, total = await self.notification_repo.list_by_user_and_organization(
            user_id=current_user.id,
            organization_id=organization_id,
            page=page,
            page_size=page_size,
        )
        return NotificationListResponse(
            items=[self._to_summary(notification) for notification in notifications],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_unread_count(
        self,
        *,
        current_user: User,
        organization_id: str,
    ) -> NotificationUnreadCountResponse:
        """Return the unread notification count for one caller scope."""
        unread_count = await self.notification_repo.get_unread_count(
            user_id=current_user.id,
            organization_id=organization_id,
        )
        return NotificationUnreadCountResponse(unread_count=unread_count)

    async def mark_as_read(
        self,
        *,
        current_user: User,
        organization_id: str,
        notification_id: str,
    ) -> NotificationMarkReadResponse:
        """Mark one owned notification as read."""
        owned_notification = await self.notification_repo.find_owned_notification(
            notification_id=notification_id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        if owned_notification is None:
            raise await self._resolve_missing_or_forbidden(notification_id)

        notification = await self.notification_repo.mark_as_read(
            notification_id=notification_id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        if notification is None:
            raise NotificationNotFoundError()

        return NotificationMarkReadResponse(
            id=notification.id,
            is_read=notification.is_read,
            read_at=notification.read_at or notification.updated_at,
        )

    async def mark_all_as_read(
        self,
        *,
        current_user: User,
        organization_id: str,
    ) -> NotificationMarkAllReadResponse:
        """Mark all unread notifications as read for one caller scope."""
        updated_count, read_at = await self.notification_repo.mark_all_as_read(
            user_id=current_user.id,
            organization_id=organization_id,
        )
        return NotificationMarkAllReadResponse(
            updated_count=updated_count,
            marked_all_read=True,
            read_at=read_at,
        )

    async def _resolve_missing_or_forbidden(
        self,
        notification_id: str,
    ) -> NotificationNotFoundError | NotificationOwnershipError:
        """Distinguish missing notifications from invalid ownership access."""
        notification = await self.notification_repo.find_by_id(
            notification_id=notification_id
        )
        if notification is None:
            return NotificationNotFoundError()
        return NotificationOwnershipError()

    @staticmethod
    async def _emit_created_event(notification: Notification) -> None:
        """Emit one realtime notification-created event to the owning user."""
        from app.socket_gateway import gateway

        await gateway.emit_to_user(
            user_id=notification.user_id,
            event=NotificationEvents.CREATED,
            data=NotificationService._to_summary(notification).model_dump(
                exclude_none=True
            ),
            organization_id=notification.organization_id,
        )

    @staticmethod
    def _to_summary(notification: Notification) -> NotificationSummary:
        """Project one persisted notification into the frontend summary shape."""
        return NotificationSummary(
            id=notification.id,
            user_id=notification.user_id,
            organization_id=notification.organization_id,
            type=notification.type,
            title=notification.title,
            body=notification.body,
            target_type=notification.target_type,
            target_id=notification.target_id,
            link=notification.link,
            actor_id=notification.actor_id,
            metadata=notification.metadata,
            is_read=notification.is_read,
            read_at=notification.read_at,
            created_at=notification.created_at,
        )

    @staticmethod
    def _require_non_blank_text(value: str, *, field_name: str) -> str:
        """Normalize one required string field for notification creation."""
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be blank")
        return normalized

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        """Collapse blank optional text values to null."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("optional notification fields must be strings or None")
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_metadata(
        metadata: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Copy notification metadata into a plain dict when provided."""
        if metadata is None:
            return None
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be a mapping or None")
        normalized = dict(metadata)
        return normalized or None
