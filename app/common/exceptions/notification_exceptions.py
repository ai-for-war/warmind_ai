"""Notification-specific application exceptions."""

from app.common.exceptions import AppException


class NotificationNotFoundError(AppException):
    """Raised when a notification is missing or outside caller scope."""

    default_message = "Notification not found"
    status_code = 404


class NotificationOwnershipError(AppException):
    """Raised when a caller tries to mutate a notification they do not own."""

    default_message = "Notification does not belong to the current user"
    status_code = 403
