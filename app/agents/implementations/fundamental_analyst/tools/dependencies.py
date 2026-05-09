"""Lazy service dependency access for fundamental analyst tools."""

from __future__ import annotations

from app.services.stocks.company_service import StockCompanyService
from app.services.stocks.financial_report_service import StockFinancialReportService


def get_stock_company_service() -> StockCompanyService:
    """Load the shared stock company service lazily to avoid import cycles."""
    from app.common.service import get_stock_company_service as get_service

    return get_service()


def get_stock_financial_report_service() -> StockFinancialReportService:
    """Load the shared stock financial report service lazily to avoid import cycles."""
    from app.common.service import get_stock_financial_report_service as get_service

    return get_service()

