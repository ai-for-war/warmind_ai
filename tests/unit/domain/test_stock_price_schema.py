from __future__ import annotations

from app.domain.schemas.stock_price import (
    StockPriceHistoryQuery,
    StockPriceHistoryResponse,
    StockPriceIntradayQuery,
    StockPriceIntradayResponse,
)


def test_history_query_defaults_source_to_kbs() -> None:
    query = StockPriceHistoryQuery(start="2026-04-01")

    assert query.source == "KBS"


def test_history_query_blank_source_uses_kbs_default() -> None:
    query = StockPriceHistoryQuery(source=" ", start="2026-04-01")

    assert query.source == "KBS"


def test_intraday_query_defaults_source_to_vci() -> None:
    query = StockPriceIntradayQuery()

    assert query.source == "VCI"


def test_history_response_defaults_source_to_kbs() -> None:
    response = StockPriceHistoryResponse(symbol="FPT", items=[])

    assert response.source == "KBS"


def test_intraday_response_defaults_source_to_vci() -> None:
    response = StockPriceIntradayResponse(symbol="FPT", items=[])

    assert response.source == "VCI"
