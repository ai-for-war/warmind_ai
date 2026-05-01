"""Sandbox trade-agent-specific application exceptions."""

from app.common.exceptions import AppException


class SandboxTradeSessionNotFoundError(AppException):
    """Raised when a sandbox trade session is missing or outside caller scope."""

    default_message = "Sandbox trade session not found"
    status_code = 404


class InvalidSandboxTradeSessionStateError(AppException):
    """Raised when a sandbox trade session action is invalid for its state."""

    default_message = "Invalid sandbox trade session state"
    status_code = 409
