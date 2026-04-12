from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.models.stock import StockSymbol
from app.domain.schemas.stock import StockListQuery
from app.services.stocks.refresh import StockCatalogRefreshResult
from app.services.stocks.stock_catalog_service import StockCatalogService


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _stock(
    *,
    symbol: str,
    organ_name: str | None = None,
    exchange: str | None = None,
    groups: list[str] | None = None,
) -> StockSymbol:
    return StockSymbol(
        symbol=symbol,
        organ_name=organ_name,
        exchange=exchange,
        groups=groups or [],
        snapshot_at=_utc(2026, 4, 12),
        updated_at=_utc(2026, 4, 12, 1),
    )


class _FakeRepository:
    def __init__(self) -> None:
        self.list_paginated_calls: list[tuple[int, int]] = []
        self.find_filtered_calls: list[dict[str, object]] = []
        self.unfiltered_result: tuple[list[StockSymbol], int] = ([], 0)
        self.filtered_result: tuple[list[StockSymbol], int] = ([], 0)

    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[StockSymbol], int]:
        self.list_paginated_calls.append((page, page_size))
        return self.unfiltered_result

    async def find_filtered(
        self,
        *,
        q: str | None = None,
        exchange: str | None = None,
        group: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockSymbol], int]:
        self.find_filtered_calls.append(
            {
                "q": q,
                "exchange": exchange,
                "group": group,
                "page": page,
                "page_size": page_size,
            }
        )
        return self.filtered_result


class _FakeCache:
    def __init__(self) -> None:
        self.cached_pages: dict[tuple[int, int], object] = {}
        self.get_calls: list[tuple[int, int]] = []
        self.set_calls: list[tuple[int, int]] = []
        self.invalidate_calls = 0

    async def get_page(self, *, page: int, page_size: int):
        self.get_calls.append((page, page_size))
        return self.cached_pages.get((page, page_size))

    async def set_page(self, *, page: int, page_size: int, response) -> None:
        self.set_calls.append((page, page_size))
        self.cached_pages[(page, page_size)] = response

    async def invalidate_all(self) -> int:
        self.invalidate_calls += 1
        self.cached_pages.clear()
        return 1


class _FakeRefresher:
    def __init__(
        self,
        *,
        result: StockCatalogRefreshResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or StockCatalogRefreshResult(source="VCI", upserted=2)
        self.error = error
        self.calls = 0

    async def refresh(self) -> StockCatalogRefreshResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_list_stocks_uses_cache_for_unfiltered_requests() -> None:
    repository = _FakeRepository()
    cache = _FakeCache()
    refresher = _FakeRefresher()
    service = StockCatalogService(repository=repository, refresher=refresher, cache=cache)

    first_response = await service.list_stocks(StockListQuery(page=1, page_size=20))
    second_response = await service.list_stocks(StockListQuery(page=1, page_size=20))

    assert first_response.total == 0
    assert second_response.total == 0
    assert repository.list_paginated_calls == [(1, 20)]
    assert cache.get_calls == [(1, 20), (1, 20)]
    assert cache.set_calls == [(1, 20)]


@pytest.mark.asyncio
async def test_list_stocks_bypasses_cache_for_filtered_requests() -> None:
    repository = _FakeRepository()
    repository.filtered_result = (
        [_stock(symbol="FPT", organ_name="FPT", exchange="HOSE", groups=["VN30"])],
        1,
    )
    cache = _FakeCache()
    refresher = _FakeRefresher()
    service = StockCatalogService(repository=repository, refresher=refresher, cache=cache)

    response = await service.list_stocks(
        StockListQuery(q="fpt", exchange="hose", group="vn30", page=1, page_size=20)
    )

    assert [item.symbol for item in response.items] == ["FPT"]
    assert repository.find_filtered_calls == [
        {
            "q": "fpt",
            "exchange": "HOSE",
            "group": "VN30",
            "page": 1,
            "page_size": 20,
        }
    ]
    assert cache.get_calls == []
    assert cache.set_calls == []


@pytest.mark.asyncio
async def test_refresh_catalog_invalidates_cache_after_successful_refresh() -> None:
    repository = _FakeRepository()
    cache = _FakeCache()
    cache.cached_pages[(1, 20)] = object()
    refresher = _FakeRefresher(
        result=StockCatalogRefreshResult(source="VCI", upserted=12)
    )
    service = StockCatalogService(repository=repository, refresher=refresher, cache=cache)

    response = await service.refresh_catalog()

    assert response.status == "success"
    assert response.source == "VCI"
    assert response.upserted == 12
    assert refresher.calls == 1
    assert cache.invalidate_calls == 1
    assert cache.cached_pages == {}


@pytest.mark.asyncio
async def test_refresh_catalog_does_not_invalidate_cache_when_refresh_fails() -> None:
    repository = _FakeRepository()
    cache = _FakeCache()
    cache.cached_pages[(1, 20)] = object()
    refresher = _FakeRefresher(error=RuntimeError("refresh failed"))
    service = StockCatalogService(repository=repository, refresher=refresher, cache=cache)

    with pytest.raises(RuntimeError, match="refresh failed"):
        await service.refresh_catalog()

    assert refresher.calls == 1
    assert cache.invalidate_calls == 0
    assert (1, 20) in cache.cached_pages
