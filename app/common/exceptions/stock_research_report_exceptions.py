"""Stock research report-specific application exceptions."""

from app.common.exceptions import AppException


class StockResearchReportNotFoundError(AppException):
    """Raised when a stock research report is missing or outside caller scope."""

    default_message = "Stock research report not found"
    status_code = 404


class StockResearchReportEnqueueError(AppException):
    """Raised when a stock research report cannot be queued for processing."""

    default_message = "Stock research report could not be queued"
    status_code = 502
