"""Stock watchlist-specific application exceptions."""

from app.common.exceptions import AppException


class StockSymbolNotFoundError(AppException):
    """Raised when a stock symbol is missing from the active stock catalog."""

    default_message = "Stock symbol not found"
    status_code = 404


class StockWatchlistNotFoundError(AppException):
    """Raised when a stock watchlist is missing or outside caller scope."""

    default_message = "Stock watchlist not found"
    status_code = 404


class DuplicateStockWatchlistNameError(AppException):
    """Raised when a watchlist name already exists in the same user/org scope."""

    default_message = "Stock watchlist name already exists"
    status_code = 409


class DuplicateStockWatchlistItemError(AppException):
    """Raised when a symbol is already saved in the same watchlist."""

    default_message = "Stock symbol already exists in this watchlist"
    status_code = 409


class StockWatchlistItemNotFoundError(AppException):
    """Raised when a saved symbol is missing from a watchlist."""

    default_message = "Stock watchlist item not found"
    status_code = 404
