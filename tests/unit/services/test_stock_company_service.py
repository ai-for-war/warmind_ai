from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

import app.services.stocks.company_service as company_service_module
from app.domain.schemas.stock_company import StockCompanyOverviewResponse
from app.services.stocks.company_service import StockCompanyService


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


class _FakeRepository:
    def __init__(self, *, existing_symbols: set[str] | None = None) -> None:
        self.existing_symbols = {item.upper() for item in existing_symbols or set()}
        self.calls: list[str] = []

    async def exists_by_symbol(self, symbol: str) -> bool:
        self.calls.append(symbol)
        return symbol.upper() in self.existing_symbols


class _FakeCache:
    def __init__(self) -> None:
        self.payloads: dict[tuple[str, str, str | None], object] = {}
        self.get_calls: list[tuple[str, str, str | None]] = []
        self.set_calls: list[tuple[str, str, str | None]] = []

    async def get_response(
        self,
        *,
        symbol: str,
        section: str,
        response_model: type[object],
        variant: str | None = None,
    ):
        self.get_calls.append((symbol, section, variant))
        return self.payloads.get((symbol, section, variant))

    async def set_response(
        self,
        *,
        symbol: str,
        section: str,
        response,
        variant: str | None = None,
    ) -> None:
        self.set_calls.append((symbol, section, variant))
        self.payloads[(symbol, section, variant)] = response


class _StaleFallbackCache(_FakeCache):
    def __init__(self, stale_payload: object) -> None:
        super().__init__()
        self.stale_payload = stale_payload
        self.calls = 0

    async def get_response(
        self,
        *,
        symbol: str,
        section: str,
        response_model: type[object],
        variant: str | None = None,
    ):
        self.calls += 1
        if self.calls == 1:
            return None
        return self.stale_payload


class _FakeGateway:
    SOURCE = "VCI"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.fail_sections: set[str] = set()

    def fetch_overview(self, symbol: str) -> dict[str, object]:
        self.calls.append(("overview", symbol, None))
        if "overview" in self.fail_sections:
            raise RuntimeError("overview failed")
        return {
            "symbol": symbol,
            "company_profile": f"Company {symbol}",
        }

    def fetch_shareholders(self, symbol: str) -> list[dict[str, object]]:
        self.calls.append(("shareholders", symbol, None))
        if "shareholders" in self.fail_sections:
            raise RuntimeError("shareholders failed")
        return [{"id": 1, "share_holder": "Holder"}]

    def fetch_officers(
        self,
        symbol: str,
        *,
        filter_by: str = "working",
    ) -> list[dict[str, object]]:
        self.calls.append(("officers", symbol, filter_by))
        if "officers" in self.fail_sections:
            raise RuntimeError("officers failed")
        return [{"id": 1, "officer_name": "CEO"}]

    def fetch_subsidiaries(
        self,
        symbol: str,
        *,
        filter_by: str = "all",
    ) -> list[dict[str, object]]:
        self.calls.append(("subsidiaries", symbol, filter_by))
        if "subsidiaries" in self.fail_sections:
            raise RuntimeError("subsidiaries failed")
        return [{"id": 1, "organ_name": "Subsidiary"}]

    def fetch_affiliate(self, symbol: str) -> list[dict[str, object]]:
        self.calls.append(("affiliate", symbol, None))
        return [{"id": 1, "organ_name": "Affiliate"}]

    def fetch_events(self, symbol: str) -> list[dict[str, object]]:
        self.calls.append(("events", symbol, None))
        return [{"id": 1, "event_title": "Dividend"}]

    def fetch_news(self, symbol: str) -> list[dict[str, object]]:
        self.calls.append(("news", symbol, None))
        if "news" in self.fail_sections:
            raise RuntimeError("news failed")
        return [{"id": 1, "news_title": "Expansion"}]

    def fetch_reports(self, symbol: str) -> list[dict[str, object]]:
        self.calls.append(("reports", symbol, None))
        return [{"name": "Report"}]

    def fetch_ratio_summary(self, symbol: str) -> dict[str, object]:
        self.calls.append(("ratio-summary", symbol, None))
        return {"symbol": symbol, "year_report": 2025}

    def fetch_trading_stats(self, symbol: str) -> dict[str, object]:
        self.calls.append(("trading-stats", symbol, None))
        return {"symbol": symbol, "match_price": 100}


@pytest.mark.asyncio
async def test_overview_cache_hit_skips_upstream_and_marks_cache_hit() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    cache.payloads[("FPT", "overview", None)] = StockCompanyOverviewResponse(
        symbol="FPT",
        fetched_at=_utc(2026, 4, 13),
        item={"symbol": "FPT", "company_profile": "Cached"},
    )
    service = StockCompanyService(repository, gateway, cache)

    response = await service.get_overview("fpt")

    assert response.cache_hit is True
    assert response.item.company_profile == "Cached"
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_overview_cache_miss_fetches_upstream_and_caches_response() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockCompanyService(repository, gateway, cache)

    response = await service.get_overview(" fpt ")

    assert response.cache_hit is False
    assert response.symbol == "FPT"
    assert response.item.company_profile == "Company FPT"
    assert gateway.calls == [("overview", "FPT", None)]
    assert cache.set_calls == [("FPT", "overview", None)]


@pytest.mark.asyncio
async def test_invalid_symbol_is_rejected_before_upstream_call() -> None:
    repository = _FakeRepository(existing_symbols={"VCB"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockCompanyService(repository, gateway, cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_overview("fpt")

    assert exc_info.value.status_code == 404
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_stale_cache_is_returned_when_upstream_fails() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    gateway = _FakeGateway()
    stale_response = StockCompanyOverviewResponse(
        symbol="FPT",
        fetched_at=_utc(2026, 4, 13),
        item={"symbol": "FPT", "company_profile": "Cached"},
    )
    cache = _StaleFallbackCache(stale_response)
    gateway.fail_sections.add("overview")
    gateway.fail_sections.add("news")
    service = StockCompanyService(repository, gateway, cache)

    response = await service.get_overview("FPT")

    assert response.cache_hit is True
    assert response.item.company_profile == "Cached"


@pytest.mark.asyncio
async def test_section_specific_variant_keys_are_used_for_officers() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockCompanyService(repository, gateway, cache)

    response = await service.get_officers("fpt", filter_by="resigned")

    assert response.cache_hit is False
    assert gateway.calls == [("officers", "FPT", "resigned")]
    assert cache.set_calls == [("FPT", "officers", "filter=resigned")]


@pytest.mark.asyncio
async def test_one_failing_section_does_not_block_other_sections() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    gateway.fail_sections.add("overview")
    service = StockCompanyService(repository, gateway, cache)

    with pytest.raises(RuntimeError, match="overview failed"):
        await service.get_overview("FPT")

    news = await service.get_news("FPT")

    assert news.items[0].news_title == "Expansion"
    assert ("news", "FPT", None) in gateway.calls


@pytest.mark.asyncio
async def test_service_offloads_gateway_fetches_to_threadpool(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockCompanyService(repository, gateway, cache)
    threadpool_calls: list[tuple[object, str]] = []

    async def _fake_run_in_threadpool(func, *args, **kwargs):
        assert not kwargs
        threadpool_calls.append((func, args[0]))
        return func(*args)

    monkeypatch.setattr(
        company_service_module,
        "run_in_threadpool",
        _fake_run_in_threadpool,
    )

    response = await service.get_overview("FPT")

    assert response.item.company_profile == "Company FPT"
    assert threadpool_calls == [(gateway.fetch_overview, "FPT")]
