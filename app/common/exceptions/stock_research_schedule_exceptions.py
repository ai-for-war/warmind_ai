"""Stock research schedule-specific application exceptions."""

from app.common.exceptions import AppException


class StockResearchScheduleNotFoundError(AppException):
    """Raised when a stock research schedule is missing or outside caller scope."""

    default_message = "Stock research schedule not found"
    status_code = 404


class StockResearchScheduleDispatchError(AppException):
    """Raised when a stock research schedule report cannot be enqueued."""

    default_message = "Stock research schedule dispatch failed"
    status_code = 502
