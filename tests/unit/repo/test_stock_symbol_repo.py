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
    industry_code: int | None = None,
) -> dict[str, object]:
    stock = StockSymbol(
        symbol=symbol,
        organ_name=organ_name,
        exchange=exchange,
        groups=groups or [],
        industry_code=industry_code,
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
            if "$ne" in expected:
                if actual == expected["$ne"]:
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

    async def bulk_write(self, operations: list[object], ordered: bool = True) -> None:
        for operation in operations:
            query = deepcopy(operation._filter)
            update = deepcopy(operation._doc)
            await self.find_one_and_update(
                query,
                update,
                upsert=operation._upsert,
                return_document=ReturnDocument.AFTER,
            )

    async def delete_many(self, query: dict[str, object]):
        retained: list[dict[str, object]] = []
        deleted_count = 0
        for document in self._documents:
            if _matches_query(document, query):
                deleted_count += 1
                continue
            retained.append(document)
        self._documents = retained

        class _Result:
            def __init__(self, count: int) -> None:
                self.deleted_count = count

        return _Result(deleted_count)


class _FakeMetadataCollection:
    def __init__(self, metadata: dict[str, dict[str, object]] | None = None) -> None:
        self._documents = deepcopy(metadata or {})

    async def find_one(self, query: dict[str, object]) -> dict[str, object] | None:
        document_id = query.get("_id")
        if not isinstance(document_id, str):
            return None
        document = self._documents.get(document_id)
        return deepcopy(document) if isinstance(document, dict) else None

    async def find_one_and_update(
        self,
        query: dict[str, object],
        update: dict[str, dict[str, object]],
        *,
        upsert: bool = False,
        return_document: ReturnDocument | bool | None = None,
    ) -> dict[str, object] | None:
        document_id = query.get("_id")
        if not isinstance(document_id, str):
            return None

        current = deepcopy(self._documents.get(document_id, {"_id": document_id}))
        if document_id not in self._documents and not upsert:
            return None

        updated = deepcopy(current)
        for field_name, value in update.get("$set", {}).items():
            updated[field_name] = value
        self._documents[document_id] = updated
        if return_document == ReturnDocument.AFTER:
            return deepcopy(updated)
        return deepcopy(current)


class _FakeDB:
    def __init__(
        self,
        documents: list[dict[str, object]],
        *,
        active_snapshot_at: datetime | None = None,
    ) -> None:
        self.stock_symbols = _FakeStockCollection(documents)
        metadata = None
        if active_snapshot_at is not None:
            metadata = {
                StockSymbolRepository.SNAPSHOT_META_ID: {
                    "_id": StockSymbolRepository.SNAPSHOT_META_ID,
                    "snapshot_at": active_snapshot_at,
                }
            }
        self.stock_catalog_metadata = _FakeMetadataCollection(metadata)


@pytest.mark.asyncio
async def test_list_paginated_returns_sorted_page_and_total() -> None:
    repository = StockSymbolRepository(
        _FakeDB(
            [
                _stock_document(symbol="VCB", organ_name="Vietcombank", exchange="HOSE"),
                _stock_document(symbol="ACB", organ_name="ACB", exchange="HNX"),
                _stock_document(symbol="FPT", organ_name="FPT", exchange="HOSE"),
            ],
            active_snapshot_at=_utc(2026, 4, 12),
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
            ],
            active_snapshot_at=_utc(2026, 4, 12),
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
            ],
            active_snapshot_at=_utc(2026, 4, 12),
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
async def test_find_filtered_supports_industry_code_filter() -> None:
    repository = StockSymbolRepository(
        _FakeDB(
            [
                _stock_document(symbol="FPT", organ_name="FPT", exchange="HOSE", industry_code=9500),
                _stock_document(symbol="VCB", organ_name="VCB", exchange="HOSE", industry_code=8300),
                _stock_document(symbol="MBB", organ_name="MBB", exchange="HOSE", industry_code=8300),
            ],
            active_snapshot_at=_utc(2026, 4, 12),
        )
    )

    items, total = await repository.find_filtered(
        industry_code=8300,
        page=1,
        page_size=10,
    )

    assert [item.symbol for item in items] == ["MBB", "VCB"]
    assert total == 2


@pytest.mark.asyncio
async def test_upsert_replaces_existing_symbol_document() -> None:
    repository = StockSymbolRepository(
        _FakeDB(
            [
                _stock_document(symbol="FPT", organ_name="Old Name", exchange="HOSE"),
            ],
            active_snapshot_at=_utc(2026, 4, 12),
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


@pytest.mark.asyncio
async def test_list_paginated_only_returns_active_snapshot() -> None:
    repository = StockSymbolRepository(
        _FakeDB(
            [
                _stock_document(symbol="AAA", organ_name="Old AAA", exchange="HOSE"),
                _stock_document(symbol="BBB", organ_name="Old BBB", exchange="HOSE"),
                {
                    **_stock_document(symbol="CCC", organ_name="New CCC", exchange="HOSE"),
                    "snapshot_at": _utc(2026, 4, 13),
                    "updated_at": _utc(2026, 4, 13, 1),
                },
            ],
            active_snapshot_at=_utc(2026, 4, 13),
        )
    )

    items, total = await repository.list_paginated(page=1, page_size=10)

    assert [item.symbol for item in items] == ["CCC"]
    assert total == 1


@pytest.mark.asyncio
async def test_replace_snapshot_marks_new_snapshot_active_and_prunes_old_symbols() -> None:
    db = _FakeDB(
        [
            _stock_document(symbol="SSI", organ_name="SSI", exchange="HOSE"),
            _stock_document(symbol="VCI", organ_name="VCI", exchange="HOSE"),
        ],
        active_snapshot_at=_utc(2026, 4, 12),
    )
    repository = StockSymbolRepository(db)
    snapshot_at = _utc(2026, 4, 13)

    upserted = await repository.replace_snapshot(
        [
            StockSymbol(
                symbol="FPT",
                organ_name="FPT",
                exchange="HOSE",
                snapshot_at=snapshot_at,
                updated_at=snapshot_at,
            ),
            StockSymbol(
                symbol="VCB",
                organ_name="VCB",
                exchange="HOSE",
                snapshot_at=snapshot_at,
                updated_at=snapshot_at,
            ),
        ],
        snapshot_at=snapshot_at,
    )

    assert upserted == 2
    assert await repository.get_active_snapshot_at() == snapshot_at
    symbols = sorted(document["symbol"] for document in db.stock_symbols._documents)
    assert symbols == ["FPT", "VCB"]
