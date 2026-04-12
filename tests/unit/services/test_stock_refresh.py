from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.models.stock import StockSymbol
from app.services.stocks.refresh import StockCatalogSnapshotRefresher


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


class _FakeGateway:
    SOURCE = "VCI"

    def __init__(self) -> None:
        self.group_requests: list[tuple[str, ...]] = []

    def fetch_all_symbols(self) -> list[dict[str, object]]:
        return [
            {"symbol": "FPT", "organ_name": "Cong ty Co phan FPT"},
            {"symbol": "VCB", "organ_name": "Ngan hang Vietcombank"},
        ]

    def fetch_symbols_by_exchange(self) -> list[dict[str, object]]:
        return [
            {"symbol": "FPT", "exchange": "HOSE"},
            {"symbol": "VCB", "exchange": "HOSE"},
        ]

    def fetch_symbols_by_industries(self) -> list[dict[str, object]]:
        return [
            {"symbol": "FPT", "industry_code": "8300", "industry_name": "Cong nghe"},
        ]

    def fetch_group_memberships(self, groups: tuple[str, ...]) -> dict[str, list[str]]:
        self.group_requests.append(tuple(groups))
        return {"FPT": ["VN30"], "VCB": ["VN30", "VN100"]}


class _FailingGateway(_FakeGateway):
    def fetch_symbols_by_exchange(self) -> list[dict[str, object]]:
        raise RuntimeError("VCI unavailable")


class _FakeRepository:
    def __init__(self, existing: list[StockSymbol] | None = None) -> None:
        self.persisted: list[StockSymbol] = list(existing or [])
        self.upsert_calls: list[str] = []

    async def upsert(self, stock_symbol: StockSymbol) -> StockSymbol:
        self.upsert_calls.append(stock_symbol.symbol)
        self.persisted = [
            item for item in self.persisted if item.symbol != stock_symbol.symbol
        ]
        self.persisted.append(stock_symbol)
        return stock_symbol


@pytest.mark.asyncio
async def test_refresh_upserts_full_snapshot() -> None:
    gateway = _FakeGateway()
    repository = _FakeRepository()
    refresher = StockCatalogSnapshotRefresher(gateway, repository)

    result = await refresher.refresh()

    assert result.source == "VCI"
    assert result.upserted == 2
    assert repository.upsert_calls == ["FPT", "VCB"]
    assert gateway.group_requests
    assert {item.symbol for item in repository.persisted} == {"FPT", "VCB"}


@pytest.mark.asyncio
async def test_refresh_failure_preserves_previous_snapshot() -> None:
    existing = [
        StockSymbol(
            symbol="SSI",
            organ_name="SSI",
            exchange="HOSE",
            snapshot_at=_utc(2026, 4, 11),
            updated_at=_utc(2026, 4, 11, 1),
        )
    ]
    repository = _FakeRepository(existing=existing)
    refresher = StockCatalogSnapshotRefresher(_FailingGateway(), repository)

    with pytest.raises(RuntimeError, match="VCI unavailable"):
        await refresher.refresh()

    assert repository.upsert_calls == []
    assert [item.symbol for item in repository.persisted] == ["SSI"]
