"""Stock-chat-specific application exceptions."""

from app.common.exceptions import AppException


class StockChatConversationNotFoundError(AppException):
    """Raised when a stock-chat conversation is missing or outside caller scope."""

    default_message = "Stock-chat conversation not found"
    status_code = 404


class StockChatClarificationNotImplementedError(AppException):
    """Raised while the stock-chat clarification service is not wired yet."""

    default_message = "Stock-chat clarification service is not implemented yet"
    status_code = 501


class StockChatClarificationAgentError(AppException):
    """Raised when the stock-chat clarification agent cannot return valid output."""

    default_message = "Stock-chat clarification agent failed"
    status_code = 502


class StockChatDownstreamNotImplementedError(AppException):
    """Raised when clarification is complete but downstream handling is absent."""

    default_message = "Stock-chat downstream processing is not implemented yet"
    status_code = 501
