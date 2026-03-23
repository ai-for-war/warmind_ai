from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re

import pytest
from pymongo import DESCENDING, ReturnDocument

from app.domain.models.meeting import Meeting, MeetingArchiveScope, MeetingStatus
from app.repo.meeting_repo import MeetingRepository


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _meeting_document(
    *,
    meeting_id: str,
    organization_id: str = "org-1",
    created_by: str = "user-1",
    title: str | None = "Weekly sync",
    source: str = "google_meet",
    status: MeetingStatus = MeetingStatus.COMPLETED,
    started_at: datetime | None = None,
    archived_at: datetime | None = None,
    archived_by: str | None = None,
) -> dict[str, object]:
    meeting = Meeting(
        _id=meeting_id,
        organization_id=organization_id,
        created_by=created_by,
        title=title,
        source=source,
        status=status,
        language="en",
        stream_id=f"stream-{meeting_id}",
        started_at=started_at or _utc(2026, 1, 1),
        ended_at=None,
        error_message=None,
        archived_at=archived_at,
        archived_by=archived_by,
    )
    return meeting.model_dump(by_alias=True, mode="python")


def _matches_query(document: dict[str, object], query: dict[str, object]) -> bool:
    for field_name, expected in query.items():
        actual = document.get(field_name)
        if isinstance(expected, dict):
            regex = expected.get("$regex")
            if regex is not None:
                flags = re.IGNORECASE if "i" in expected.get("$options", "") else 0
                text = actual or ""
                if not isinstance(text, str) or re.search(regex, text, flags) is None:
                    return False

            for operator, value in expected.items():
                if operator in {"$regex", "$options"}:
                    continue
                if operator == "$gte" and (actual is None or actual < value):
                    return False
                if operator == "$lte" and (actual is None or actual > value):
                    return False
                if operator == "$ne" and actual == value:
                    return False
        elif actual != expected:
            return False
    return True


def _apply_update(document: dict[str, object], update: dict[str, dict[str, object]]) -> None:
    for field_name, value in update.get("$set", {}).items():
        document[field_name] = value

    for field_name in update.get("$unset", {}):
        document.pop(field_name, None)


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


class _FakeMeetingCollection:
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
        upsert: bool = False,
        return_document: ReturnDocument | bool | None = None,
    ) -> dict[str, object] | None:
        for index, document in enumerate(self._documents):
            if not _matches_query(document, query):
                continue

            before_update = deepcopy(document)
            updated = deepcopy(document)
            _apply_update(updated, update)
            self._documents[index] = updated
            if return_document == ReturnDocument.AFTER:
                return deepcopy(updated)
            return before_update

        if not upsert:
            return None

        created = deepcopy(update.get("$setOnInsert", {}))
        self._documents.append(created)
        return deepcopy(created)


class _FakeDB:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.meetings = _FakeMeetingCollection(documents)


@pytest.mark.asyncio
async def test_list_for_creator_applies_creator_scope_filters_and_title_search() -> None:
    repository = MeetingRepository(
        _FakeDB(
            [
                _meeting_document(
                    meeting_id="meeting-1",
                    title="Weekly Sync",
                    started_at=_utc(2026, 1, 10, 9),
                ),
                _meeting_document(
                    meeting_id="meeting-2",
                    title="Daily sync",
                    started_at=_utc(2026, 1, 12, 9),
                ),
                _meeting_document(
                    meeting_id="meeting-3",
                    title="Budget sync",
                    status=MeetingStatus.FAILED,
                    started_at=_utc(2026, 1, 11, 9),
                ),
                _meeting_document(
                    meeting_id="meeting-4",
                    created_by="user-2",
                    title="Other creator sync",
                    started_at=_utc(2026, 1, 12, 10),
                ),
                _meeting_document(
                    meeting_id="meeting-5",
                    organization_id="org-2",
                    title="Other org sync",
                    started_at=_utc(2026, 1, 12, 11),
                ),
                _meeting_document(
                    meeting_id="meeting-6",
                    title="Archived sync",
                    started_at=_utc(2026, 1, 12, 12),
                    archived_at=_utc(2026, 1, 13, 8),
                    archived_by="user-1",
                ),
            ]
        )
    )

    items = await repository.list_for_creator(
        organization_id="org-1",
        created_by="user-1",
        scope=MeetingArchiveScope.ACTIVE,
        status=MeetingStatus.COMPLETED,
        started_at_from=_utc(2026, 1, 10),
        started_at_to=_utc(2026, 1, 12, 23),
        q="SYNC",
        skip=0,
        limit=10,
    )
    total = await repository.count_for_creator(
        organization_id="org-1",
        created_by="user-1",
        scope=MeetingArchiveScope.ACTIVE,
        status=MeetingStatus.COMPLETED,
        started_at_from=_utc(2026, 1, 10),
        started_at_to=_utc(2026, 1, 12, 23),
        q="sync",
    )

    assert [item.id for item in items] == ["meeting-2", "meeting-1"]
    assert total == 2


@pytest.mark.asyncio
async def test_list_for_creator_honors_archive_scope_variants() -> None:
    repository = MeetingRepository(
        _FakeDB(
            [
                _meeting_document(
                    meeting_id="meeting-1",
                    title="Active older",
                    started_at=_utc(2026, 1, 10, 9),
                ),
                _meeting_document(
                    meeting_id="meeting-2",
                    title="Archived newest",
                    started_at=_utc(2026, 1, 13, 9),
                    archived_at=_utc(2026, 1, 14, 8),
                    archived_by="user-1",
                ),
                _meeting_document(
                    meeting_id="meeting-3",
                    title="Active newer",
                    started_at=_utc(2026, 1, 12, 9),
                ),
            ]
        )
    )

    active_items = await repository.list_for_creator(
        organization_id="org-1",
        created_by="user-1",
        scope=MeetingArchiveScope.ACTIVE,
    )
    archived_items = await repository.list_for_creator(
        organization_id="org-1",
        created_by="user-1",
        scope=MeetingArchiveScope.ARCHIVED,
    )
    all_items = await repository.list_for_creator(
        organization_id="org-1",
        created_by="user-1",
        scope=MeetingArchiveScope.ALL,
    )

    assert [item.id for item in active_items] == ["meeting-3", "meeting-1"]
    assert [item.id for item in archived_items] == ["meeting-2"]
    assert [item.id for item in all_items] == ["meeting-2", "meeting-3", "meeting-1"]


@pytest.mark.asyncio
async def test_update_metadata_for_creator_updates_and_restores_archive_state() -> None:
    repository = MeetingRepository(
        _FakeDB(
            [
                _meeting_document(
                    meeting_id="meeting-1",
                    title="Original title",
                    source="google_meet",
                    started_at=_utc(2026, 1, 10, 9),
                )
            ]
        )
    )

    archived_at = _utc(2026, 1, 15, 10)
    archived = await repository.update_metadata_for_creator(
        meeting_id="meeting-1",
        organization_id="org-1",
        created_by="user-1",
        title="Renamed title",
        source="zoom",
        archived=True,
        archived_by="user-1",
        archived_at=archived_at,
    )
    restored = await repository.update_metadata_for_creator(
        meeting_id="meeting-1",
        organization_id="org-1",
        created_by="user-1",
        archived=False,
    )

    assert archived is not None
    assert archived.title == "Renamed title"
    assert archived.source == "zoom"
    assert archived.archived_at == archived_at
    assert archived.archived_by == "user-1"

    assert restored is not None
    assert restored.title == "Renamed title"
    assert restored.source == "zoom"
    assert restored.archived_at is None
    assert restored.archived_by is None
