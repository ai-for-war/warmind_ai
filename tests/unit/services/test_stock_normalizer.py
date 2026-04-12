from __future__ import annotations

from datetime import datetime, timezone

from app.services.stocks.normalizer import build_stock_symbol_snapshot


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def test_build_stock_symbol_snapshot_merges_listing_views() -> None:
    snapshot = build_stock_symbol_snapshot(
        all_symbols=[
            {"symbol": "fpt", "organ_name": "Cong ty Co phan FPT"},
            {"symbol": "vcb", "organ_name": "Ngan hang Vietcombank"},
        ],
        symbols_by_exchange=[
            {"symbol": "FPT", "exchange": "hose"},
            {"symbol": "VCB", "exchange": "HOSE"},
        ],
        symbols_by_industries=[
            {"symbol": "FPT", "icb_code2": "8300", "icb_name2": "Cong nghe"},
        ],
        group_memberships={
            "FPT": ["VN30", "VN100"],
            "VCB": ["VN30"],
        },
        now=_utc(2026, 4, 12),
    )

    assert [item.symbol for item in snapshot] == ["FPT", "VCB"]

    fpt = snapshot[0]
    assert fpt.organ_name == "Cong ty Co phan FPT"
    assert fpt.exchange == "HOSE"
    assert fpt.groups == ["VN100", "VN30"]
    assert fpt.industry_code == 8300
    assert fpt.industry_name == "Cong nghe"
    assert fpt.snapshot_at == _utc(2026, 4, 12)
    assert fpt.updated_at == _utc(2026, 4, 12)


def test_build_stock_symbol_snapshot_ignores_invalid_records_and_creates_group_only_symbols() -> None:
    snapshot = build_stock_symbol_snapshot(
        all_symbols=[
            None,
            {"organ_name": "Missing symbol"},
            {"symbol": "abc", "organ_name": "ABC"},
        ],
        symbols_by_exchange=[],
        symbols_by_industries=[],
        group_memberships={"XYZ": ["vn30", "VN30"]},
        source="VCI",
        now=_utc(2026, 4, 12),
    )

    assert [item.symbol for item in snapshot] == ["ABC", "XYZ"]
    assert snapshot[1].groups == ["VN30"]
    assert snapshot[1].source == "VCI"
