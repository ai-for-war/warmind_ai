"""Stock research report-specific application exceptions."""

from app.common.exceptions import AppException


class StockResearchReportNotFoundError(AppException):
    """Raised when a stock research report is missing or outside caller scope."""

    default_message = "Stock research report not found"
    status_code = 404
