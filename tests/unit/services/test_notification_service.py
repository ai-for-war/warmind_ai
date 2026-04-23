from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.socket_gateway as socket_gateway_module
from app.common.event_socket import NotificationEvents
from app.common.exceptions import (
    NotificationNotFoundError,
    NotificationOwnershipError,
)
from app.domain.models.notification import Notification
from app.domain.models.user import User, UserRole
from app.services.notification_service import NotificationService


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _user(*, user_id: str = "user-1") -> User:
    now = _utc(2026, 4, 23, 8)
    return User(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _notification(
    *,
    notification_id: str = "6807dd18c5d8d14d4af1d111",
    user_id: str = "user-1",
    organization_id: str = "org-1",
    type: str = "task_assigned",
    title: str = "Task assigned",
    body: str = "Open the task",
    target_type: str = "task",
    target_id: str = "task-1",
    link: str | None = None,
    is_read: bool = False,
    read_at: datetime | None = None,
) -> Notification:
    now = _utc(2026, 4, 23, 8)
    return Notification(
        _id=notification_id,
        user_id=user_id,
        organization_id=organization_id,
        type=type,
        title=title,
        body=body,
        target_type=target_type,
        target_id=target_id,
        link=link,
        is_read=is_read,
        read_at=read_at,
        created_at=now,
        updated_at=read_at or now,
    )


def _repo(**overrides):
    defaults = {
        "find_by_dedupe_key": AsyncMock(return_value=None),
        "create": AsyncMock(),
        "list_by_user_and_organization": AsyncMock(return_value=([], 0)),
        "get_unread_count": AsyncMock(return_value=0),
        "find_owned_notification": AsyncMock(return_value=None),
        "mark_as_read": AsyncMock(return_value=None),
        "mark_all_as_read": AsyncMock(return_value=(0, _utc(2026, 4, 23, 9))),
        "find_by_id": AsyncMock(return_value=None),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_create_notification_normalizes_payload_persists_target_and_emits_realtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _notification(
        type="task_assigned",
        title="Task assigned",
        body="Open the task",
        target_type="task",
        target_id="task-42",
        link="/tasks/42?tab=activity",
    )
    repository = _repo(create=AsyncMock(return_value=created))
    fake_gateway = SimpleNamespace(emit_to_user=AsyncMock())
    monkeypatch.setattr(socket_gateway_module, "gateway", fake_gateway)
    service = NotificationService(notification_repo=repository)

    response = await service.create_notification(
        user_id="user-1",
        organization_id="org-1",
        type=" task_assigned ",
        title=" Task assigned ",
        body=" Open the task ",
        target_type=" task ",
        target_id=" task-42 ",
        link=" /tasks/42?tab=activity ",
        dedupe_key=" dedupe-1 ",
        metadata={"tab": "activity"},
    )

    repository.create.assert_awaited_once_with(
        user_id="user-1",
        organization_id="org-1",
        type="task_assigned",
        title="Task assigned",
        body="Open the task",
        target_type="task",
        target_id="task-42",
        link="/tasks/42?tab=activity",
        actor_id=None,
        dedupe_key="dedupe-1",
        metadata={"tab": "activity"},
    )
    assert response.target_type == "task"
    assert response.target_id == "task-42"
    assert response.link == "/tasks/42?tab=activity"
    assert response.is_read is False
    fake_gateway.emit_to_user.assert_awaited_once_with(
        user_id="user-1",
        event=NotificationEvents.CREATED,
        data=response.model_dump(exclude_none=True),
        organization_id="org-1",
    )


@pytest.mark.asyncio
async def test_create_notification_reuses_existing_dedupe_match_without_emitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _notification(notification_id="6807dd18c5d8d14d4af1d112")
    repository = _repo(find_by_dedupe_key=AsyncMock(return_value=existing))
    fake_gateway = SimpleNamespace(emit_to_user=AsyncMock())
    monkeypatch.setattr(socket_gateway_module, "gateway", fake_gateway)
    service = NotificationService(notification_repo=repository)

    response = await service.create_notification(
        user_id="user-1",
        organization_id="org-1",
        type="task_assigned",
        title="Task assigned",
        body="Open the task",
        target_type="task",
        target_id="task-1",
        dedupe_key="task_assigned:task-1",
    )

    assert response.id == "6807dd18c5d8d14d4af1d112"
    repository.create.assert_not_awaited()
    fake_gateway.emit_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_as_read_raises_ownership_error_for_foreign_notification() -> None:
    repository = _repo(
        find_by_id=AsyncMock(
            return_value=_notification(user_id="user-2", organization_id="org-1")
        )
    )
    service = NotificationService(notification_repo=repository)

    with pytest.raises(NotificationOwnershipError):
        await service.mark_as_read(
            current_user=_user(),
            organization_id="org-1",
            notification_id="6807dd18c5d8d14d4af1d111",
        )

    repository.mark_as_read.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_as_read_raises_not_found_when_notification_is_missing() -> None:
    service = NotificationService(notification_repo=_repo())

    with pytest.raises(NotificationNotFoundError):
        await service.mark_as_read(
            current_user=_user(),
            organization_id="org-1",
            notification_id="6807dd18c5d8d14d4af1d111",
        )
