from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId
import pytest
from pymongo import DESCENDING, ReturnDocument

from app.domain.models.notification import Notification
from app.repo.notification_repo import NotificationRepository


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _notification_document(
    *,
    notification_id: str | None = None,
    user_id: str = "user-1",
    organization_id: str = "org-1",
    type: str = "task_assigned",
    title: str = "Task assigned",
    body: str = "Open the task",
    target_type: str = "task",
    target_id: str = "task-1",
    link: str | None = None,
    dedupe_key: str | None = None,
    is_read: bool = False,
    read_at: datetime | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> dict[str, object]:
    now = created_at or _utc(2026, 4, 23, 8)
    notification = Notification(
        _id=notification_id or str(ObjectId()),
        user_id=user_id,
        organization_id=organization_id,
        type=type,
        title=title,
        body=body,
        target_type=target_type,
        target_id=target_id,
        link=link,
        dedupe_key=dedupe_key,
        is_read=is_read,
        read_at=read_at,
        created_at=now,
        updated_at=updated_at or read_at or now,
    )
    payload = notification.model_dump(by_alias=True, mode="python")
    payload["_id"] = ObjectId(payload["_id"])
    return payload


def _matches_query(document: dict[str, object], query: dict[str, object]) -> bool:
    for field_name, expected in query.items():
        if document.get(field_name) != expected:
            return False
    return True


class _FakeCursor:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = list(documents)
        self._iterator: iter[dict[str, object]] | None = None

    def sort(self, field_name: str, direction: int) -> "_FakeCursor":
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


class _FakeCollection:
    def __init__(self, documents: list[dict[str, object]] | None = None) -> None:
        self._documents = [deepcopy(document) for document in (documents or [])]

    async def insert_one(self, payload: dict[str, object]):
        document = deepcopy(payload)
        document["_id"] = ObjectId()
        self._documents.append(document)
        return SimpleNamespace(inserted_id=document["_id"])

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
        return_document: ReturnDocument,
    ) -> dict[str, object] | None:
        for index, document in enumerate(self._documents):
            if not _matches_query(document, query):
                continue

            updated = deepcopy(document)
            updated.update(update.get("$set", {}))
            self._documents[index] = updated
            if return_document == ReturnDocument.AFTER:
                return deepcopy(updated)
            return deepcopy(document)
        return None

    async def update_many(
        self,
        query: dict[str, object],
        update: dict[str, dict[str, object]],
    ):
        modified_count = 0
        for index, document in enumerate(self._documents):
            if not _matches_query(document, query):
                continue
            updated = deepcopy(document)
            updated.update(update.get("$set", {}))
            self._documents[index] = updated
            modified_count += 1
        return SimpleNamespace(modified_count=modified_count)

    def find(self, query: dict[str, object]) -> _FakeCursor:
        matched = [
            deepcopy(document)
            for document in self._documents
            if _matches_query(document, query)
        ]
        return _FakeCursor(matched)

    async def count_documents(self, query: dict[str, object]) -> int:
        return sum(1 for document in self._documents if _matches_query(document, query))


class _FakeDB:
    def __init__(self, documents: list[dict[str, object]] | None = None) -> None:
        self.notifications = _FakeCollection(documents)


@pytest.mark.asyncio
async def test_list_and_unread_count_are_scoped_and_newest_first() -> None:
    repository = NotificationRepository(
        _FakeDB(
            [
                _notification_document(
                    notification_id="6807dd18c5d8d14d4af1d111",
                    user_id="user-1",
                    organization_id="org-1",
                    created_at=_utc(2026, 4, 23, 9),
                    is_read=False,
                ),
                _notification_document(
                    notification_id="6807dd18c5d8d14d4af1d112",
                    user_id="user-1",
                    organization_id="org-1",
                    created_at=_utc(2026, 4, 23, 8),
                    is_read=True,
                    read_at=_utc(2026, 4, 23, 8),
                ),
                _notification_document(
                    user_id="user-1",
                    organization_id="org-2",
                    created_at=_utc(2026, 4, 23, 10),
                    is_read=False,
                ),
                _notification_document(
                    user_id="user-2",
                    organization_id="org-1",
                    created_at=_utc(2026, 4, 23, 11),
                    is_read=False,
                ),
            ]
        )
    )

    notifications, total = await repository.list_by_user_and_organization(
        user_id="user-1",
        organization_id="org-1",
        page=1,
        page_size=10,
    )
    unread_count = await repository.get_unread_count(
        user_id="user-1",
        organization_id="org-1",
    )

    assert total == 2
    assert [notification.id for notification in notifications] == [
        "6807dd18c5d8d14d4af1d111",
        "6807dd18c5d8d14d4af1d112",
    ]
    assert unread_count == 1


@pytest.mark.asyncio
async def test_find_by_dedupe_key_is_scoped_to_user_and_organization() -> None:
    repository = NotificationRepository(
        _FakeDB(
            [
                _notification_document(
                    notification_id="6807dd18c5d8d14d4af1d121",
                    user_id="user-1",
                    organization_id="org-1",
                    dedupe_key="task_assigned:task-1",
                ),
                _notification_document(
                    user_id="user-1",
                    organization_id="org-2",
                    dedupe_key="task_assigned:task-1",
                ),
            ]
        )
    )

    found = await repository.find_by_dedupe_key(
        user_id="user-1",
        organization_id="org-1",
        dedupe_key="task_assigned:task-1",
    )
    missing = await repository.find_by_dedupe_key(
        user_id="user-2",
        organization_id="org-1",
        dedupe_key="task_assigned:task-1",
    )

    assert found is not None
    assert found.id == "6807dd18c5d8d14d4af1d121"
    assert missing is None


@pytest.mark.asyncio
async def test_mark_as_read_updates_read_state_and_is_idempotent() -> None:
    repository = NotificationRepository(
        _FakeDB(
            [
                _notification_document(
                    notification_id="6807dd18c5d8d14d4af1d131",
                    user_id="user-1",
                    organization_id="org-1",
                    is_read=False,
                )
            ]
        )
    )

    first = await repository.mark_as_read(
        notification_id="6807dd18c5d8d14d4af1d131",
        user_id="user-1",
        organization_id="org-1",
    )
    second = await repository.mark_as_read(
        notification_id="6807dd18c5d8d14d4af1d131",
        user_id="user-1",
        organization_id="org-1",
    )

    assert first is not None
    assert first.is_read is True
    assert first.read_at is not None
    assert second is not None
    assert second.is_read is True
    assert second.read_at == first.read_at


@pytest.mark.asyncio
async def test_mark_all_as_read_updates_only_unread_notifications_in_scope() -> None:
    repository = NotificationRepository(
        _FakeDB(
            [
                _notification_document(
                    user_id="user-1",
                    organization_id="org-1",
                    is_read=False,
                ),
                _notification_document(
                    user_id="user-1",
                    organization_id="org-1",
                    is_read=False,
                ),
                _notification_document(
                    user_id="user-1",
                    organization_id="org-1",
                    is_read=True,
                    read_at=_utc(2026, 4, 23, 8),
                ),
                _notification_document(
                    user_id="user-2",
                    organization_id="org-1",
                    is_read=False,
                ),
            ]
        )
    )

    updated_count, read_at = await repository.mark_all_as_read(
        user_id="user-1",
        organization_id="org-1",
    )
    remaining_unread = await repository.get_unread_count(
        user_id="user-1",
        organization_id="org-1",
    )
    foreign_unread = await repository.get_unread_count(
        user_id="user-2",
        organization_id="org-1",
    )

    assert updated_count == 2
    assert read_at.tzinfo == timezone.utc
    assert remaining_unread == 0
    assert foreign_unread == 1
