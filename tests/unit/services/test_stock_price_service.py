from __future__ import annotations

import pytest
from fastapi import HTTPException

import app.services.stocks.price_service as price_service_module
from app.domain.schemas.stock_price import (
    StockPriceHistoryQuery,
    StockPriceHistoryResponse,
    StockPriceIntradayQuery,
    StockPriceIntradayResponse,
)
from app.services.stocks.price_service import StockPriceService


class _FakeRepository:
    def __init__(self, *, existing_symbols: set[str] | None = None) -> None:
        self.existing_symbols = {item.upper() for item in existing_symbols or set()}
        self.calls: list[str] = []

    async def exists_by_symbol(self, symbol: str) -> bool:
        self.calls.append(symbol)
        return symbol.upper() in self.existing_symbols


class _FakeCache:
    def __init__(self) -> None:
        self.payloads: dict[tuple[str, str, str], object] = {}
        self.get_calls: list[tuple[str, str, str]] = []
        self.set_calls: list[tuple[str, str, str]] = []

    async def get_response(
        self,
        *,
        symbol: str,
        section: str,
        variant: str,
        response_model: type[object],
    ):
        del response_model
        self.get_calls.append((symbol, section, variant))
        return self.payloads.get((symbol, section, variant))

    async def set_response(
        self,
        *,
        symbol: str,
        section: str,
        variant: str,
        response,
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
        variant: str,
        response_model: type[object],
    ):
        del symbol, section, variant, response_model
        self.calls += 1
        if self.calls == 1:
            return None
        return self.stale_payload


class _FakeGateway:
    SOURCE = "VCI"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object | None]]] = []
        self.fail_history = False
        self.fail_intraday = False
        self.history_error: Exception = RuntimeError("history failed")
        self.intraday_error: Exception = RuntimeError("intraday failed")

    def fetch_history(
        self,
        symbol: str,
        *,
        source: str = "VCI",
        start: str | None = None,
        end: str | None = None,
        interval: str = "1D",
        length: int | str | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            (
                "history",
                symbol,
                {
                    "source": source,
                    "start": start,
                    "end": end,
                    "interval": interval,
                    "length": length,
                },
            )
        )
        if self.fail_history:
            raise self.history_error
        return [
            {
                "time": "2026-04-15",
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.0,
                "volume": 1000,
            }
        ]

    def fetch_intraday(
        self,
        symbol: str,
        *,
        source: str = "VCI",
        page_size: int = 100,
        last_time: str | None = None,
        last_time_format: str | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            (
                "intraday",
                symbol,
                {
                    "source": source,
                    "page_size": page_size,
                    "last_time": last_time,
                    "last_time_format": last_time_format,
                },
            )
        )
        if self.fail_intraday:
            raise self.intraday_error
        return [
            {
                "time": "2026-04-15T09:15:00",
                "price": 101.2,
                "volume": 50,
                "match_type": "Buy",
                "id": 42,
            }
        ]


@pytest.mark.asyncio
async def test_history_cache_hit_skips_upstream_and_marks_cache_hit() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    query = StockPriceHistoryQuery(start="2026-04-01", interval="1D")
    variant = StockPriceService._build_history_variant(query)  # noqa: SLF001
    cache.payloads[("FPT", "history", variant)] = StockPriceHistoryResponse(
        symbol="FPT",
        source="VCI",
        cache_hit=False,
        interval="1D",
        items=[{"time": "2026-04-15", "close": 101.0}],
    )
    service = StockPriceService(repository, gateway, cache)

    response = await service.get_history("fpt", query)

    assert response.cache_hit is True
    assert response.items[0].close == 101.0
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_history_cache_miss_fetches_upstream_and_caches_response() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockPriceService(repository, gateway, cache)

    response = await service.get_history(
        " fpt ",
        StockPriceHistoryQuery(start="2026-04-01", end="2026-04-15", interval="1D"),
    )

    assert response.cache_hit is False
    assert response.symbol == "FPT"
    assert response.interval == "1D"
    assert gateway.calls == [
        (
            "history",
            "FPT",
            {
                "source": "VCI",
                "start": "2026-04-01",
                "end": "2026-04-15",
                "interval": "1D",
                "length": None,
            },
        )
    ]
    assert cache.set_calls == [
        (
            "FPT",
            "history",
            "interval=1D:start=2026-04-01:end=2026-04-15:length=",
        )
    ]


@pytest.mark.asyncio
async def test_invalid_symbol_is_rejected_before_upstream_call() -> None:
    repository = _FakeRepository(existing_symbols={"VCB"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockPriceService(repository, gateway, cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_history("fpt", StockPriceHistoryQuery(start="2026-04-01"))

    assert exc_info.value.status_code == 404
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_stale_cache_is_returned_when_history_upstream_fails() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    gateway = _FakeGateway()
    gateway.fail_history = True
    stale_response = StockPriceHistoryResponse(
        symbol="FPT",
        source="VCI",
        cache_hit=False,
        interval="1D",
        items=[{"time": "2026-04-14", "close": 99.0}],
    )
    cache = _StaleFallbackCache(stale_response)
    service = StockPriceService(repository, gateway, cache)

    response = await service.get_history(
        "FPT", StockPriceHistoryQuery(start="2026-04-01")
    )

    assert response.cache_hit is True
    assert response.items[0].close == 99.0


@pytest.mark.asyncio
async def test_query_variant_keys_are_isolated_for_intraday_reads() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockPriceService(repository, gateway, cache)

    first = await service.get_intraday(
        "fpt",
        StockPriceIntradayQuery(page_size=100),
    )
    second = await service.get_intraday(
        "fpt",
        StockPriceIntradayQuery(page_size=100, last_time="2026-04-15 09:15:00"),
    )

    assert first.cache_hit is False
    assert second.cache_hit is False
    assert cache.set_calls == [
        ("FPT", "intraday", "page_size=100:last_time=:last_time_format="),
        (
            "FPT",
            "intraday",
            "page_size=100:last_time=2026-04-15%2009%3A15%3A00:last_time_format=",
        ),
    ]


@pytest.mark.asyncio
async def test_service_maps_provider_input_errors_to_422() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    gateway.fail_history = True
    gateway.history_error = ValueError("Giá trị interval không hợp lệ: bad")
    service = StockPriceService(repository, gateway, cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_history("FPT", StockPriceHistoryQuery(start="2026-04-01"))

    assert exc_info.value.status_code == 422
    assert "interval" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_service_maps_unexpected_upstream_errors_to_502() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    gateway.fail_intraday = True
    service = StockPriceService(repository, gateway, cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_intraday("FPT", StockPriceIntradayQuery(page_size=100))

    assert exc_info.value.status_code == 502
    assert (
        exc_info.value.detail
        == "Failed to fetch stock price data from upstream provider"
    )


@pytest.mark.asyncio
async def test_one_failing_variant_does_not_block_other_variants() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockPriceService(repository, gateway, cache)

    gateway.fail_history = True
    gateway.history_error = RuntimeError("history failed")
    with pytest.raises(HTTPException) as exc_info:
        await service.get_history("FPT", StockPriceHistoryQuery(start="2026-04-01"))

    gateway.fail_history = False
    response = await service.get_history(
        "FPT", StockPriceHistoryQuery(length=30, interval="1D")
    )

    assert exc_info.value.status_code == 502
    assert response.items[0].close == 101.0
    assert cache.set_calls == [
        ("FPT", "history", "interval=1D:start=:end=:length=30"),
    ]


@pytest.mark.asyncio
async def test_service_offloads_gateway_fetches_to_threadpool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockPriceService(repository, gateway, cache)
    threadpool_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def _fake_run_in_threadpool(func, *args, **kwargs):
        threadpool_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(
        price_service_module,
        "run_in_threadpool",
        _fake_run_in_threadpool,
    )

    response = await service.get_intraday(
        "FPT",
        StockPriceIntradayQuery(page_size=120, last_time="2026-04-15 09:15:00"),
    )

    assert response.items[0].price == 101.2
    assert threadpool_calls == [
        (
            gateway.fetch_intraday,
            ("FPT",),
            {
                "source": "VCI",
                "page_size": 120,
                "last_time": "2026-04-15 09:15:00",
                "last_time_format": None,
            },
        )
    ]
