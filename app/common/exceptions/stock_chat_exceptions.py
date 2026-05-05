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
