"""Notification inbox API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.service import get_notification_service
from app.domain.models.user import User
from app.domain.schemas.notification import (
    NotificationListResponse,
    NotificationMarkAllReadResponse,
    NotificationMarkReadResponse,
    NotificationUnreadCountResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
async def get_notification_unread_count(
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationUnreadCountResponse:
    """Return the current user's unread notification count in one organization."""
    return await service.get_unread_count(
        current_user=current_user,
        organization_id=org_context.organization_id,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    """List the current user's notifications in one organization scope."""
    return await service.list_notifications(
        current_user=current_user,
        organization_id=org_context.organization_id,
        page=page,
        page_size=page_size,
    )


@router.post("/{notification_id}/read", response_model=NotificationMarkReadResponse)
async def mark_notification_as_read(
    notification_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationMarkReadResponse:
    """Mark one owned notification as read."""
    return await service.mark_as_read(
        current_user=current_user,
        organization_id=org_context.organization_id,
        notification_id=notification_id,
    )


@router.post("/read-all", response_model=NotificationMarkAllReadResponse)
async def mark_all_notifications_as_read(
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationMarkAllReadResponse:
    """Mark all owned unread notifications as read in one organization scope."""
    return await service.mark_all_as_read(
        current_user=current_user,
        organization_id=org_context.organization_id,
    )
