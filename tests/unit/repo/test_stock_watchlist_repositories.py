from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from bson import ObjectId
import pytest
from pymongo import DESCENDING, ReturnDocument

from app.repo.stock_watchlist_item_repo import StockWatchlistItemRepository
from app.repo.stock_watchlist_repo import StockWatchlistRepository


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _watchlist_document(
    *,
    watchlist_id: ObjectId | None = None,
    user_id: str,
    organization_id: str,
    name: str,
    normalized_name: str,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> dict[str, object]:
    created = created_at or _utc(2026, 4, 17)
    updated = updated_at or created
    return {
        "_id": watchlist_id or ObjectId(),
        "user_id": user_id,
        "organization_id": organization_id,
        "name": name,
        "normalized_name": normalized_name,
        "created_at": created,
        "updated_at": updated,
    }


def _item_document(
    *,
    item_id: ObjectId | None = None,
    watchlist_id: str,
    user_id: str,
    organization_id: str,
    symbol: str,
    normalized_symbol: str,
    saved_at: datetime,
    updated_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "_id": item_id or ObjectId(),
        "watchlist_id": watchlist_id,
        "user_id": user_id,
        "organization_id": organization_id,
        "symbol": symbol,
        "normalized_symbol": normalized_symbol,
        "saved_at": saved_at,
        "updated_at": updated_at or saved_at,
    }


def _matches_query(document: dict[str, object], query: dict[str, object]) -> bool:
    for field_name, expected in query.items():
        actual = document.get(field_name)
        if isinstance(expected, dict):
            if "$ne" in expected:
                if actual == expected["$ne"]:
                    return False
                continue
            return False
        if actual != expected:
            return False
    return True


class _FakeCursor:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = list(documents)
        self._iterator: iter[dict[str, object]] | None = None

    def sort(self, fields, direction: int | None = None) -> "_FakeCursor":
        normalized_fields = (
            [(fields, direction if direction is not None else DESCENDING)]
            if isinstance(fields, str)
            else list(fields)
        )
        for field_name, field_direction in reversed(normalized_fields):
            reverse = field_direction in {DESCENDING, -1}
            self._documents.sort(
                key=lambda document: document.get(field_name),
                reverse=reverse,
            )
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


class _InsertResult:
    def __init__(self, inserted_id: ObjectId) -> None:
        self.inserted_id = inserted_id


class _DeleteResult:
    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class _FakeCollection:
    def __init__(self, documents: list[dict[str, object]] | None = None) -> None:
        self._documents = [deepcopy(document) for document in documents or []]

    async def insert_one(self, payload: dict[str, object]) -> _InsertResult:
        document = deepcopy(payload)
        inserted_id = document.get("_id")
        if not isinstance(inserted_id, ObjectId):
            inserted_id = ObjectId()
            document["_id"] = inserted_id
        self._documents.append(document)
        return _InsertResult(inserted_id)

    def find(self, query: dict[str, object]) -> _FakeCursor:
        matched = [
            deepcopy(document)
            for document in self._documents
            if _matches_query(document, query)
        ]
        return _FakeCursor(matched)

    async def find_one(self, query: dict[str, object]) -> dict[str, object] | None:
        for document in self._documents:
            if _matches_query(document, query):
                return deepcopy(document)
        return None

    async def find_one_and_update(
        self,
        query: dict[str, object],
        update: dict[str, dict[str, object]],
        *,
        return_document: ReturnDocument | bool | None = None,
    ) -> dict[str, object] | None:
        for index, document in enumerate(self._documents):
            if not _matches_query(document, query):
                continue

            current = deepcopy(document)
            updated = deepcopy(document)
            for field_name, value in update.get("$set", {}).items():
                updated[field_name] = value
            self._documents[index] = updated
            if return_document == ReturnDocument.AFTER:
                return deepcopy(updated)
            return current
        return None

    async def delete_one(self, query: dict[str, object]) -> _DeleteResult:
        for index, document in enumerate(self._documents):
            if _matches_query(document, query):
                del self._documents[index]
                return _DeleteResult(1)
        return _DeleteResult(0)

    async def delete_many(self, query: dict[str, object]) -> _DeleteResult:
        retained: list[dict[str, object]] = []
        deleted_count = 0
        for document in self._documents:
            if _matches_query(document, query):
                deleted_count += 1
                continue
            retained.append(document)
        self._documents = retained
        return _DeleteResult(deleted_count)

    async def count_documents(
        self,
        query: dict[str, object],
        limit: int | None = None,
    ) -> int:
        count = 0
        for document in self._documents:
            if _matches_query(document, query):
                count += 1
                if limit is not None and count >= limit:
                    return count
        return count


class _FakeDB:
    def __init__(
        self,
        *,
        watchlists: list[dict[str, object]] | None = None,
        items: list[dict[str, object]] | None = None,
    ) -> None:
        self.stock_watchlists = _FakeCollection(watchlists)
        self.stock_watchlist_items = _FakeCollection(items)


@pytest.mark.asyncio
async def test_watchlist_duplicate_name_checks_scope_and_exclusion() -> None:
    existing_id = ObjectId()
    repository = StockWatchlistRepository(
        _FakeDB(
            watchlists=[
                _watchlist_document(
                    watchlist_id=existing_id,
                    user_id="user-1",
                    organization_id="org-1",
                    name="Tech",
                    normalized_name="tech",
                ),
                _watchlist_document(
                    user_id="user-1",
                    organization_id="org-2",
                    name="Tech",
                    normalized_name="tech",
                ),
            ]
        )
    )

    assert (
        await repository.has_duplicate_name(
            user_id="user-1",
            organization_id="org-1",
            normalized_name="tech",
        )
        is True
    )
    assert (
        await repository.has_duplicate_name(
            user_id="user-1",
            organization_id="org-1",
            normalized_name="tech",
            exclude_watchlist_id=str(existing_id),
        )
        is False
    )
    assert (
        await repository.has_duplicate_name(
            user_id="user-2",
            organization_id="org-1",
            normalized_name="tech",
        )
        is False
    )


@pytest.mark.asyncio
async def test_item_duplicate_symbol_is_scoped_per_watchlist() -> None:
    repository = StockWatchlistItemRepository(
        _FakeDB(
            items=[
                _item_document(
                    watchlist_id="watchlist-1",
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="FPT",
                    normalized_symbol="fpt",
                    saved_at=_utc(2026, 4, 17, 8, 0),
                )
            ]
        )
    )

    assert (
        await repository.has_duplicate_symbol(
            watchlist_id="watchlist-1",
            normalized_symbol="fpt",
        )
        is True
    )
    assert (
        await repository.has_duplicate_symbol(
            watchlist_id="watchlist-2",
            normalized_symbol="fpt",
        )
        is False
    )


@pytest.mark.asyncio
async def test_list_by_watchlist_returns_newest_saved_items_first() -> None:
    repository = StockWatchlistItemRepository(
        _FakeDB(
            items=[
                _item_document(
                    watchlist_id="watchlist-1",
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="VCB",
                    normalized_symbol="vcb",
                    saved_at=_utc(2026, 4, 17, 8, 0),
                ),
                _item_document(
                    watchlist_id="watchlist-1",
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="FPT",
                    normalized_symbol="fpt",
                    saved_at=_utc(2026, 4, 17, 9, 0),
                ),
                _item_document(
                    watchlist_id="watchlist-2",
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="SSI",
                    normalized_symbol="ssi",
                    saved_at=_utc(2026, 4, 17, 10, 0),
                ),
            ]
        )
    )

    items = await repository.list_by_watchlist(
        watchlist_id="watchlist-1",
        user_id="user-1",
        organization_id="org-1",
    )

    assert [item.symbol for item in items] == ["FPT", "VCB"]


@pytest.mark.asyncio
async def test_delete_by_watchlist_removes_only_target_watchlist_items() -> None:
    repository = StockWatchlistItemRepository(
        _FakeDB(
            items=[
                _item_document(
                    watchlist_id="watchlist-1",
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="FPT",
                    normalized_symbol="fpt",
                    saved_at=_utc(2026, 4, 17, 8, 0),
                ),
                _item_document(
                    watchlist_id="watchlist-1",
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="VCB",
                    normalized_symbol="vcb",
                    saved_at=_utc(2026, 4, 17, 9, 0),
                ),
                _item_document(
                    watchlist_id="watchlist-2",
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="SSI",
                    normalized_symbol="ssi",
                    saved_at=_utc(2026, 4, 17, 10, 0),
                ),
            ]
        )
    )

    deleted_count = await repository.delete_by_watchlist(
        watchlist_id="watchlist-1",
        user_id="user-1",
        organization_id="org-1",
    )

    remaining_watchlist_1 = await repository.list_by_watchlist(
        watchlist_id="watchlist-1",
        user_id="user-1",
        organization_id="org-1",
    )
    remaining_watchlist_2 = await repository.list_by_watchlist(
        watchlist_id="watchlist-2",
        user_id="user-1",
        organization_id="org-1",
    )

    assert deleted_count == 2
    assert remaining_watchlist_1 == []
    assert [item.symbol for item in remaining_watchlist_2] == ["SSI"]
