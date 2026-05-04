from __future__ import annotations

import pytest
from fastapi import HTTPException

import app.services.stocks.financial_report_service as service_module
from app.domain.schemas.stock_financial_report import (
    StockFinancialReportQuery,
    StockFinancialReportResponse,
)
from app.services.stocks.financial_report_service import StockFinancialReportService


class _FakeRepository:
    def __init__(self, *, existing_symbols: set[str] | None = None) -> None:
        self.existing_symbols = {item.upper() for item in existing_symbols or set()}
        self.calls: list[str] = []

    async def exists_by_symbol(self, symbol: str) -> bool:
        self.calls.append(symbol)
        return symbol.upper() in self.existing_symbols


class _FakeCache:
    def __init__(self) -> None:
        self.payloads: dict[tuple[str, str, str], StockFinancialReportResponse] = {}
        self.get_calls: list[tuple[str, str, str]] = []
        self.set_calls: list[tuple[str, str, str]] = []

    async def get_response(
        self,
        *,
        symbol: str,
        report_type: str,
        period: str,
    ) -> StockFinancialReportResponse | None:
        self.get_calls.append((symbol, report_type, period))
        return self.payloads.get((symbol, report_type, period))

    async def set_response(
        self,
        *,
        symbol: str,
        report_type: str,
        period: str,
        response: StockFinancialReportResponse,
    ) -> None:
        self.set_calls.append((symbol, report_type, period))
        self.payloads[(symbol, report_type, period)] = response


class _StaleFallbackCache(_FakeCache):
    def __init__(self, stale_payload: StockFinancialReportResponse) -> None:
        super().__init__()
        self.stale_payload = stale_payload
        self.calls = 0

    async def get_response(
        self,
        *,
        symbol: str,
        report_type: str,
        period: str,
    ) -> StockFinancialReportResponse | None:
        self.get_calls.append((symbol, report_type, period))
        self.calls += 1
        if self.calls == 1:
            return None
        return self.stale_payload


class _FakeGateway:
    SOURCE = "KBS"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.fail = False
        self.empty = False
        self.error: Exception = RuntimeError("upstream failed")

    def fetch_report(
        self,
        symbol: str,
        *,
        report_type: str,
        period: str,
    ) -> dict[str, object]:
        self.calls.append((symbol, report_type, period))
        if self.fail:
            raise self.error
        return {
            "symbol": symbol,
            "source": self.SOURCE,
            "report_type": report_type,
            "period": period,
            "periods": ["2025-Q4"],
            "items": []
            if self.empty
            else [
                {
                    "item": "Revenue",
                    "item_id": "revenue",
                    "values": {"2025-Q4": 100},
                }
            ],
        }


def _response(
    *,
    symbol: str = "FPT",
    report_type: str = "income-statement",
    period: str = "quarter",
) -> StockFinancialReportResponse:
    return StockFinancialReportResponse(
        symbol=symbol,
        source="KBS",
        report_type=report_type,
        period=period,
        periods=["2025-Q4"],
        cache_hit=False,
        items=[
            {
                "item": "Revenue",
                "item_id": "revenue",
                "values": {"2025-Q4": 99},
            }
        ],
    )


@pytest.mark.asyncio
async def test_report_cache_hit_skips_upstream_and_marks_cache_hit() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    cache.payloads[("FPT", "income-statement", "quarter")] = _response()
    service = StockFinancialReportService(repository, gateway, cache)

    response = await service.get_report(
        "fpt",
        "income-statement",
        StockFinancialReportQuery(),
    )

    assert response.cache_hit is True
    assert response.items[0].values == {"2025-Q4": 99}
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_report_cache_miss_fetches_upstream_and_caches_response() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockFinancialReportService(repository, gateway, cache)

    response = await service.get_report(
        " fpt ",
        "balance-sheet",
        StockFinancialReportQuery(period=" Year "),
    )

    assert response.cache_hit is False
    assert response.symbol == "FPT"
    assert response.report_type == "balance-sheet"
    assert response.period == "year"
    assert gateway.calls == [("FPT", "balance-sheet", "year")]
    assert cache.set_calls == [("FPT", "balance-sheet", "year")]


@pytest.mark.asyncio
async def test_unknown_symbol_is_rejected_before_cache_or_upstream_call() -> None:
    repository = _FakeRepository(existing_symbols={"VCB"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockFinancialReportService(repository, gateway, cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_report("fpt", "income-statement", StockFinancialReportQuery())

    assert exc_info.value.status_code == 404
    assert repository.calls == ["FPT"]
    assert cache.get_calls == []
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_invalid_report_type_is_rejected_before_symbol_lookup() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockFinancialReportService(repository, gateway, cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_report("FPT", "overview", StockFinancialReportQuery())

    assert exc_info.value.status_code == 422
    assert repository.calls == []
    assert cache.get_calls == []
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_stale_cache_is_returned_when_upstream_fails() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    gateway = _FakeGateway()
    gateway.fail = True
    cache = _StaleFallbackCache(_response())
    service = StockFinancialReportService(repository, gateway, cache)

    response = await service.get_report(
        "FPT",
        "income-statement",
        StockFinancialReportQuery(),
    )

    assert response.cache_hit is True
    assert response.items[0].values == {"2025-Q4": 99}
    assert cache.get_calls == [
        ("FPT", "income-statement", "quarter"),
        ("FPT", "income-statement", "quarter"),
    ]


@pytest.mark.asyncio
async def test_empty_upstream_rows_return_404_without_caching() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    gateway.empty = True
    service = StockFinancialReportService(repository, gateway, cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_report("FPT", "ratio", StockFinancialReportQuery())

    assert exc_info.value.status_code == 404
    assert cache.set_calls == []


@pytest.mark.asyncio
async def test_no_data_value_error_returns_404_without_stale_fallback() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _StaleFallbackCache(_response())
    gateway = _FakeGateway()
    gateway.fail = True
    gateway.error = ValueError("Không tìm thấy dữ liệu tài chính cho mã FPT.")
    service = StockFinancialReportService(repository, gateway, cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_report("FPT", "cash-flow", StockFinancialReportQuery())

    assert exc_info.value.status_code == 404
    assert cache.get_calls == [("FPT", "cash-flow", "quarter")]


@pytest.mark.asyncio
async def test_unexpected_upstream_error_without_stale_cache_returns_502() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    gateway.fail = True
    service = StockFinancialReportService(repository, gateway, cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_report("FPT", "ratio", StockFinancialReportQuery())

    assert exc_info.value.status_code == 502
    assert (
        exc_info.value.detail
        == "Failed to fetch stock financial report data from upstream provider"
    )


@pytest.mark.asyncio
async def test_cache_variants_are_isolated_by_report_type_and_period() -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockFinancialReportService(repository, gateway, cache)

    income = await service.get_report(
        "FPT",
        "income-statement",
        StockFinancialReportQuery(period="quarter"),
    )
    ratio = await service.get_report(
        "FPT",
        "ratio",
        StockFinancialReportQuery(period="year"),
    )

    assert income.report_type == "income-statement"
    assert income.period == "quarter"
    assert ratio.report_type == "ratio"
    assert ratio.period == "year"
    assert cache.set_calls == [
        ("FPT", "income-statement", "quarter"),
        ("FPT", "ratio", "year"),
    ]


@pytest.mark.asyncio
async def test_service_offloads_gateway_fetch_to_threadpool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _FakeRepository(existing_symbols={"FPT"})
    cache = _FakeCache()
    gateway = _FakeGateway()
    service = StockFinancialReportService(repository, gateway, cache)
    threadpool_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def _fake_run_in_threadpool(func, *args, **kwargs):
        threadpool_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(service_module, "run_in_threadpool", _fake_run_in_threadpool)

    await service.get_report("FPT", "cash-flow", StockFinancialReportQuery())

    assert threadpool_calls == [
        (
            gateway.fetch_report,
            ("FPT",),
            {"report_type": "cash-flow", "period": "quarter"},
        )
    ]
