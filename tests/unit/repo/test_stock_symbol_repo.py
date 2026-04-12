from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re

import pytest
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from app.domain.models.stock import StockSymbol
from app.repo.stock_symbol_repo import StockSymbolRepository


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _stock_document(
    *,
    symbol: str,
    organ_name: str | None = None,
    exchange: str | None = None,
    groups: list[str] | None = None,
) -> dict[str, object]:
    stock = StockSymbol(
        symbol=symbol,
        organ_name=organ_name,
        exchange=exchange,
        groups=groups or [],
        snapshot_at=_utc(2026, 4, 12),
        updated_at=_utc(2026, 4, 12, 1),
    )
    return stock.model_dump(by_alias=True, mode="python")


def _matches_query(document: dict[str, object], query: dict[str, object]) -> bool:
    for field_name, expected in query.items():
        if field_name == "$or":
            if not any(_matches_query(document, branch) for branch in expected):
                return False
            continue

        actual = document.get(field_name)
        if isinstance(expected, dict):
            regex = expected.get("$regex")
            if regex is not None:
                flags = re.IGNORECASE if "i" in expected.get("$options", "") else 0
                text = actual or ""
                if not isinstance(text, str) or re.search(regex, text, flags) is None:
                    return False
                continue
        elif isinstance(actual, list):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


class _FakeCursor:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = list(documents)
        self._iterator: iter[dict[str, object]] | None = None

    def sort(self, fields: list[tuple[str, int]]) -> "_FakeCursor":
        for field_name, direction in reversed(fields):
            reverse = direction in {DESCENDING, -1}
            self._documents.sort(
                key=lambda document: document.get(field_name),
                reverse=reverse,
            )
        return self

    def skip(self, count: int) -> "_FakeCursor":
        self._documents = self._documents[count:]
        return self

    def limit(self, count: int) -> "_FakeCursor":
        self._documents = self._documents[:count]
        return self

    def __aiter__(self) -> "_FakeCursor":
        self._iterator = iter(self._documents)
        return self

    async def __anext__(self) -> dict[str, object]:
        if self._iterator is None:
            self._iterator = iter(self._documents)
        try:
            return deepcopy(next(self._iterator))
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeStockCollection:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = [deepcopy(document) for document in documents]

    def find(self, query: dict[str, object]) -> _FakeCursor:
        matched = [
            deepcopy(document)
            for document in self._documents
            if _matches_query(document, query)
        ]
        return _FakeCursor(matched)

    async def count_documents(self, query: dict[str, object]) -> int:
        return sum(1 for document in self._documents if _matches_query(document, query))

    async def find_one_and_update(
        self,
        query: dict[str, object],
        update: dict[str, dict[str, object]],
        *,
        upsert: bool = False,
        return_document: ReturnDocument | bool | None = None,
    ) -> dict[str, object] | None:
        for index, document in enumerate(self._documents):
            if not _matches_query(document, query):
                continue

            updated = deepcopy(document)
            for field_name, value in update.get("$set", {}).items():
                updated[field_name] = value
            self._documents[index] = updated
            if return_document == ReturnDocument.AFTER:
                return deepcopy(updated)
            return deepcopy(document)

        if not upsert:
            return None

        created = deepcopy(update.get("$set", {}))
        self._documents.append(created)
        return deepcopy(created)


class _FakeDB:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.stock_symbols = _FakeStockCollection(documents)


@pytest.mark.asyncio
async def test_list_paginated_returns_sorted_page_and_total() -> None:
    repository = StockSymbolRepository(
        _FakeDB(
            [
                _stock_document(symbol="VCB", organ_name="Vietcombank", exchange="HOSE"),
                _stock_document(symbol="ACB", organ_name="ACB", exchange="HNX"),
                _stock_document(symbol="FPT", organ_name="FPT", exchange="HOSE"),
            ]
        )
    )

    items, total = await repository.list_paginated(page=1, page_size=2)

    assert [item.symbol for item in items] == ["ACB", "FPT"]
    assert total == 3


@pytest.mark.asyncio
async def test_find_filtered_supports_symbol_or_name_query() -> None:
    repository = StockSymbolRepository(
        _FakeDB(
            [
                _stock_document(symbol="FPT", organ_name="Cong ty Co phan FPT", exchange="HOSE"),
                _stock_document(symbol="VCB", organ_name="Ngan hang Vietcombank", exchange="HOSE"),
                _stock_document(symbol="ACB", organ_name="Asia Commercial Bank", exchange="HNX"),
            ]
        )
    )

    items, total = await repository.find_filtered(q="vietcom", page=1, page_size=10)

    assert [item.symbol for item in items] == ["VCB"]
    assert total == 1


@pytest.mark.asyncio
async def test_find_filtered_supports_exchange_and_group_filters() -> None:
    repository = StockSymbolRepository(
        _FakeDB(
            [
                _stock_document(symbol="FPT", organ_name="FPT", exchange="HOSE", groups=["VN30"]),
                _stock_document(symbol="VCB", organ_name="VCB", exchange="HOSE", groups=["VN100"]),
                _stock_document(symbol="SHS", organ_name="SHS", exchange="HNX", groups=["HNX30"]),
            ]
        )
    )

    items, total = await repository.find_filtered(
        exchange="hose",
        group="vn30",
        page=1,
        page_size=10,
    )

    assert [item.symbol for item in items] == ["FPT"]
    assert total == 1


@pytest.mark.asyncio
async def test_upsert_replaces_existing_symbol_document() -> None:
    repository = StockSymbolRepository(
        _FakeDB(
            [
                _stock_document(symbol="FPT", organ_name="Old Name", exchange="HOSE"),
            ]
        )
    )

    persisted = await repository.upsert(
        StockSymbol(
            symbol="fpt",
            organ_name="New Name",
            exchange="hose",
            groups=["vn30"],
            snapshot_at=_utc(2026, 4, 13),
            updated_at=_utc(2026, 4, 13, 1),
        )
    )

    assert persisted.symbol == "FPT"
    assert persisted.organ_name == "New Name"
    assert persisted.groups == ["VN30"]
    assert persisted.snapshot_at == _utc(2026, 4, 13)
