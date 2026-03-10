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


class ImageNotFoundError(AppException):
    """Raised when image is not found or already deleted."""

    default_message = "Image not found"
    status_code = 404


class ImageUploadError(AppException):
    """Raised when image upload to external storage fails."""

    default_message = "Image upload failed"
    status_code = 500


class InvalidImageTypeError(AppException):
    """Raised when uploaded file MIME type is not allowed."""

    default_message = "Invalid image type"
    status_code = 400


class FileSizeLimitExceededError(AppException):
    """Raised when uploaded file exceeds maximum allowed size."""

    default_message = "File size exceeds 25MB limit"
    status_code = 413


class VoiceNotFoundError(AppException):
    """Raised when voice is not found or already deleted."""

    default_message = "Voice not found"
    status_code = 404


class AudioFileNotFoundError(AppException):
    """Raised when audio file is not found or already deleted."""

    default_message = "Audio file not found"
    status_code = 404


class VoiceCloneError(AppException):
    """Raised when voice cloning operation fails."""

    default_message = "Voice cloning provider failed"
    status_code = 502


class InvalidAudioTypeError(AppException):
    """Raised when uploaded audio MIME type is not allowed."""

    default_message = "Invalid audio type"
    status_code = 400


class AudioFileSizeLimitExceededError(AppException):
    """Raised when uploaded audio file exceeds maximum allowed size."""

    default_message = "Audio file size exceeds 20MB limit"
    status_code = 413


class MiniMaxAPIError(AppException):
    """Raised when MiniMax API returns an error response."""

    default_message = "MiniMax API request failed"
    status_code = 502

    def __init__(self, message: str = None, minimax_status_code: int | None = None):
        self.minimax_status_code = minimax_status_code
        super().__init__(message)


class MiniMaxRateLimitError(MiniMaxAPIError):
    """Raised when MiniMax API rate limit is exceeded."""

    default_message = "MiniMax rate limit exceeded"
    status_code = 429


class MiniMaxStreamError(MiniMaxAPIError):
    """Raised when MiniMax streaming synthesis fails."""

    default_message = "MiniMax audio stream failed"
    status_code = 502


class ImageGenerationJobNotFoundError(AppException):
    """Raised when an image generation job is not found."""

    default_message = "Image generation job not found"
    status_code = 404


class InvalidImageGenerationJobStateError(AppException):
    """Raised when a generation job is in an invalid state for an operation."""

    default_message = "Invalid image generation job state"
    status_code = 409


class ImageGenerationCancellationConflictError(AppException):
    """Raised when cancellation cannot be applied due to a race or state transition."""

    default_message = "Image generation job can no longer be cancelled"
    status_code = 409


class ImageGenerationProviderError(AppException):
    """Raised when text-to-image provider execution fails."""

    default_message = "Image generation provider failed"
    status_code = 502


class ImageGenerationRetryableProviderError(ImageGenerationProviderError):
    """Raised when provider failure is transient and safe to retry."""

    default_message = "Image generation provider temporarily unavailable"
    status_code = 502

    def __init__(self, message: str = None, provider_code: int | None = None):
        self.provider_code = provider_code
        super().__init__(message)


class ImageGenerationNonRetryableProviderError(ImageGenerationProviderError):
    """Raised when provider rejects request and retry is not useful."""

    default_message = "Image generation request rejected by provider"
    status_code = 422

    def __init__(self, message: str = None, provider_code: int | None = None):
        self.provider_code = provider_code
        super().__init__(message)


class ImageGenerationStorageError(AppException):
    """Raised when storing generated image output fails."""

    default_message = "Image generation storage failed"
    status_code = 502
