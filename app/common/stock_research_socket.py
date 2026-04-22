"""Shared payload builders for stock-research socket events."""

from app.domain.models.stock_research_report import StockResearchReport


def build_stock_research_terminal_payload(*, report: StockResearchReport) -> dict:
    """Return the normalized realtime payload for one terminal report update."""
    return {
        "report_id": report.id,
        "symbol": report.symbol,
        "status": report.status.value,
        "completed_at": report.completed_at,
        "error": (
            None
            if report.error is None
            else {
                "code": report.error.code,
                "message": report.error.message,
            }
        ),
    }
