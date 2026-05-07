"""Lazy service dependency access for technical analyst tools."""

from __future__ import annotations

from app.services.backtest.service import BacktestService
from app.services.stocks.price_service import StockPriceService


def get_stock_price_service() -> StockPriceService:
    """Load the shared stock price service lazily to avoid import cycles."""
    from app.common.service import get_stock_price_service as get_service

    return get_service()


def get_backtest_service() -> BacktestService:
    """Load the shared backtest service lazily to avoid import cycles."""
    from app.common.service import get_backtest_service as get_service

    return get_service()
