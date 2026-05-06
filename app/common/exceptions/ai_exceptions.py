"""AI-specific application exceptions."""

from app.common.exceptions import AppException


class InvalidLeadAgentThreadError(AppException):
    """Raised when a lead-agent thread identifier is malformed."""

    default_message = "Invalid lead-agent thread ID"
    status_code = 400


class LeadAgentThreadNotFoundError(AppException):
    """Raised when a lead-agent thread is missing or outside caller scope."""

    default_message = "Lead-agent thread not found"
    status_code = 404


class LeadAgentConversationNotFoundError(AppException):
    """Raised when a lead-agent conversation is missing or outside caller scope."""

    default_message = "Lead-agent conversation not found"
    status_code = 404


class LeadAgentSkillNotFoundError(AppException):
    """Raised when a lead-agent skill is missing or outside caller scope."""

    default_message = "Lead-agent skill not found"
    status_code = 404


class InvalidLeadAgentSkillConfigurationError(AppException):
    """Raised when a lead-agent skill request is invalid."""

    default_message = "Invalid lead-agent skill configuration"
    status_code = 400


class LeadAgentRunError(AppException):
    """Raised when a lead-agent run does not yield a usable response."""

    default_message = "Lead-agent run did not return a final assistant response"
    status_code = 502


class InvalidStockAgentThreadError(AppException):
    """Raised when a stock-agent thread identifier is malformed."""

    default_message = "Invalid stock-agent thread ID"
    status_code = 400


class StockAgentThreadNotFoundError(AppException):
    """Raised when a stock-agent thread is missing or outside caller scope."""

    default_message = "Stock-agent thread not found"
    status_code = 404


class StockAgentConversationNotFoundError(AppException):
    """Raised when a stock-agent conversation is missing or outside caller scope."""

    default_message = "Stock-agent conversation not found"
    status_code = 404


class StockAgentSkillNotFoundError(AppException):
    """Raised when a stock-agent skill is missing or outside caller scope."""

    default_message = "Stock-agent skill not found"
    status_code = 404


class InvalidStockAgentSkillConfigurationError(AppException):
    """Raised when a stock-agent skill request is invalid."""

    default_message = "Invalid stock-agent skill configuration"
    status_code = 400


class StockAgentRunError(AppException):
    """Raised when a stock-agent run does not yield a usable response."""

    default_message = "Stock-agent run did not return a final assistant response"
    status_code = 502
