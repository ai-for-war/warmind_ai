from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.models.stock import StockSymbol
from app.domain.schemas.stock import StockListQuery


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def test_stock_symbol_normalizes_persisted_fields() -> None:
    stock = StockSymbol(
        symbol=" fpt ",
        organ_name="  Cong ty Co phan FPT  ",
        exchange=" hose ",
        groups=[" vn30 ", "VN30", " vn100 "],
        industry_code="8300",
        industry_name="  Cong nghe ",
        source=" vci ",
        snapshot_at=_utc(2026, 4, 12),
        updated_at=_utc(2026, 4, 12, 1),
    )

    assert stock.id == "FPT"
    assert stock.symbol == "FPT"
    assert stock.normalized_symbol == "fpt"
    assert stock.organ_name == "Cong ty Co phan FPT"
    assert stock.normalized_organ_name == "cong ty co phan fpt"
    assert stock.exchange == "HOSE"
    assert stock.groups == ["VN30", "VN100"]
    assert stock.industry_code == 8300
    assert stock.industry_name == "Cong nghe"
    assert stock.source == "VCI"


def test_stock_symbol_collapses_blank_optional_fields() -> None:
    stock = StockSymbol(
        symbol="acb",
        organ_name="   ",
        exchange="",
        groups=[" ", "vn30", "vn30"],
        industry_code="",
        industry_name=" ",
        snapshot_at=_utc(2026, 4, 12),
        updated_at=_utc(2026, 4, 12, 1),
    )

    assert stock.organ_name is None
    assert stock.normalized_organ_name is None
    assert stock.exchange is None
    assert stock.groups == ["VN30"]
    assert stock.industry_code is None
    assert stock.industry_name is None
    assert stock.source == "VCI"


def test_stock_list_query_normalizes_filters() -> None:
    query = StockListQuery(
        q="  FPT  ",
        exchange=" hose ",
        group=" vn30 ",
        page=2,
        page_size=50,
    )

    assert query.q == "FPT"
    assert query.exchange == "HOSE"
    assert query.group == "VN30"
    assert query.page == 2
    assert query.page_size == 50


def test_stock_list_query_treats_blank_filters_as_absent() -> None:
    query = StockListQuery(q=" ", exchange=" ", group=" ")

    assert query.q is None
    assert query.exchange is None
    assert query.group is None


def test_stock_symbol_rejects_non_string_groups() -> None:
    with pytest.raises(TypeError):
        StockSymbol(
            symbol="SSI",
            groups=["VN30", 123],
            snapshot_at=_utc(2026, 4, 12),
            updated_at=_utc(2026, 4, 12, 1),
        )
