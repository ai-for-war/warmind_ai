from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.schemas.stock_company import StockCompanyOverviewResponse
from app.services.stocks.company_cache import StockCompanyCache


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


class _FakeRedis:
    def __init__(self) -> None:
        self.payloads: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.payloads.get(key)

    async def setex(self, key: str, ttl: int, payload: str) -> None:
        self.payloads[key] = payload

    async def scan_iter(self, match: str):
        prefix = match[:-1]
        for key in list(self.payloads):
            if key.startswith(prefix):
                yield key

    async def unlink(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.payloads:
                del self.payloads[key]
                deleted += 1
        return deleted


@pytest.mark.asyncio
async def test_company_cache_round_trips_section_response() -> None:
    redis = _FakeRedis()
    cache = StockCompanyCache(redis)
    response = StockCompanyOverviewResponse(
        symbol="FPT",
        fetched_at=_utc(2026, 4, 13),
        item={"symbol": "FPT", "company_profile": "FPT"},
    )

    await cache.set_response(symbol="fpt", section="overview", response=response)
    cached = await cache.get_response(
        symbol="FPT",
        section="overview",
        response_model=StockCompanyOverviewResponse,
    )

    assert cached is not None
    assert cached.symbol == "FPT"
    assert cached.item.company_profile == "FPT"


@pytest.mark.asyncio
async def test_company_cache_uses_variant_in_key_and_invalidates_symbol_namespace() -> None:
    redis = _FakeRedis()
    cache = StockCompanyCache(redis)
    response = StockCompanyOverviewResponse(
        symbol="FPT",
        fetched_at=_utc(2026, 4, 13),
        item={"symbol": "FPT", "company_profile": "FPT"},
    )

    await cache.set_response(
        symbol="fpt",
        section="officers",
        variant="filter=resigned",
        response=response,
    )
    await cache.set_response(
        symbol="fpt",
        section="news",
        response=response,
    )
    deleted = await cache.invalidate_symbol("FPT")

    assert deleted == 2
    assert redis.payloads == {}
