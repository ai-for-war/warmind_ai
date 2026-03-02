"""Custom exceptions for the application."""


class AppException(Exception):
    """Base exception for application errors."""

    default_message: str = "An error occurred"
    status_code: int = 400

    def __init__(self, message: str = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class AuthenticationError(AppException):
    """Raised when authentication fails (invalid email or password)."""

    default_message = "Invalid email or password"
    status_code = 401


class InvalidTokenError(AppException):
    """Raised when JWT token is invalid or expired."""

    default_message = "Invalid token"
    status_code = 401


class EmailAlreadyExistsError(AppException):
    """Raised when email is already registered."""

    default_message = "Email already registered"
    status_code = 409


class UserNotFoundError(AppException):
    """Raised when user is not found."""

    default_message = "User not found"
    status_code = 404


class OrganizationNotFoundError(AppException):
    """Raised when organization is not found."""

    default_message = "Organization not found"
    status_code = 404


class AlreadyMemberError(AppException):
    """Raised when user is already an active member of organization."""

    default_message = "Already a member"
    status_code = 400


class NotMemberError(AppException):
    """Raised when user is not a member of organization."""

    default_message = "Not a member"
    status_code = 404


class InactiveUserError(AppException):
    """Raised when user account is inactive."""

    default_message = "Account is inactive"
    status_code = 403


class PermissionDeniedError(AppException):
    """Raised when user lacks required permissions."""

    default_message = "Permission denied"
    status_code = 403
