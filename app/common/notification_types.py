"""Canonical notification type constants.

Keep notification type identifiers centralized so business flows and tests do
not drift into ad-hoc string literals.
"""


class NotificationTypes:
    """Notification type identifiers used by in-app inbox producers."""

    STOCK_RESEARCH_REPORT_COMPLETED = "stock_research_report_completed"
    STOCK_RESEARCH_REPORT_FAILED = "stock_research_report_failed"


class NotificationTargetTypes:
    """Notification target-type identifiers for deep-link semantics."""

    STOCK_RESEARCH_REPORT = "stock_research_report"
