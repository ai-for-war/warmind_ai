from __future__ import annotations

from datetime import datetime, timezone
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

service_module = ModuleType("app.common.service")
service_module.get_auth_service = lambda: SimpleNamespace()
service_module.get_notification_service = lambda: None
sys.modules.setdefault("app.common.service", service_module)

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.notifications import router as notifications_router
from app.common.exceptions import AppException
from app.common.notification_types import NotificationTargetTypes, NotificationTypes
from app.common.repo import get_member_repo, get_org_repo
from app.common.service import get_notification_service
from app.domain.models.user import User, UserRole
from app.domain.schemas.notification import (
    NotificationListResponse,
    NotificationMarkAllReadResponse,
    NotificationMarkReadResponse,
    NotificationSummary,
    NotificationUnreadCountResponse,
)


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _user(*, user_id: str = "user-1", role: UserRole = UserRole.USER) -> User:
    now = _utc(2026, 4, 23, 8)
    return User(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _summary(
    *,
    notification_id: str = "notif-1",
    type: str = NotificationTypes.STOCK_RESEARCH_REPORT_COMPLETED,
    title: str = "FPT research report is ready",
    body: str = "Open the FPT research report to review the completed analysis.",
    target_type: str = NotificationTargetTypes.STOCK_RESEARCH_REPORT,
    target_id: str = "report-1",
    link: str | None = "/stock-research/reports/report-1",
    is_read: bool = False,
) -> NotificationSummary:
    now = _utc(2026, 4, 23, 8)
    return NotificationSummary(
        id=notification_id,
        user_id="user-1",
        organization_id="org-1",
        type=type,
        title=title,
        body=body,
        target_type=target_type,
        target_id=target_id,
        link=link,
        actor_id=None,
        metadata={"symbol": "FPT"},
        is_read=is_read,
        read_at=None,
        created_at=now,
    )


class _FakeNotificationService:
    def __init__(self) -> None:
        self.unread_calls: list[dict[str, object]] = []
        self.list_calls: list[dict[str, object]] = []
        self.mark_one_calls: list[dict[str, object]] = []
        self.mark_all_calls: list[dict[str, object]] = []
        self.unread_response = NotificationUnreadCountResponse(unread_count=2)
        self.list_response = NotificationListResponse(
            items=[_summary(notification_id="notif-2"), _summary(notification_id="notif-1")],
            total=2,
            page=1,
            page_size=20,
        )
        self.mark_one_response = NotificationMarkReadResponse(
            id="notif-1",
            is_read=True,
            read_at=_utc(2026, 4, 23, 9),
        )
        self.mark_all_response = NotificationMarkAllReadResponse(
            updated_count=2,
            marked_all_read=True,
            read_at=_utc(2026, 4, 23, 9),
        )

    async def get_unread_count(self, **kwargs) -> NotificationUnreadCountResponse:
        self.unread_calls.append(kwargs)
        return self.unread_response

    async def list_notifications(self, **kwargs) -> NotificationListResponse:
        self.list_calls.append(kwargs)
        return self.list_response.model_copy(
            update={
                "page": kwargs.get("page", self.list_response.page),
                "page_size": kwargs.get("page_size", self.list_response.page_size),
            }
        )

    async def mark_as_read(self, **kwargs) -> NotificationMarkReadResponse:
        self.mark_one_calls.append(kwargs)
        return self.mark_one_response

    async def mark_all_as_read(self, **kwargs) -> NotificationMarkAllReadResponse:
        self.mark_all_calls.append(kwargs)
        return self.mark_all_response


class _FakeOrganization:
    def __init__(self, *, is_active: bool = True) -> None:
        self.is_active = is_active


class _FakeOrganizationRepo:
    def __init__(self, active_org_ids: set[str] | None = None) -> None:
        self.active_org_ids = {"org-1"} if active_org_ids is None else active_org_ids

    async def find_by_id(self, organization_id: str):
        if organization_id in self.active_org_ids:
            return _FakeOrganization(is_active=True)
        return None


class _FakeMembership:
    def __init__(self, *, role: str = "member") -> None:
        self.role = role


class _FakeMemberRepo:
    def __init__(self, memberships: set[tuple[str, str]] | None = None) -> None:
        self.memberships = {("user-1", "org-1")} if memberships is None else memberships

    async def find_by_user_and_org(
        self,
        *,
        user_id: str,
        organization_id: str,
        is_active: bool,
    ):
        del is_active
        if (user_id, organization_id) in self.memberships:
            return _FakeMembership()
        return None


def _build_test_app(
    *,
    service: _FakeNotificationService,
    use_real_org_context: bool = True,
    org_repo: _FakeOrganizationRepo | None = None,
    member_repo: _FakeMemberRepo | None = None,
) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        del request
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    app.include_router(notifications_router, prefix="/api/v1")
    app.dependency_overrides[get_notification_service] = lambda: service
    app.dependency_overrides[get_current_active_user] = lambda: _user()

    if use_real_org_context:
        app.dependency_overrides[get_org_repo] = lambda: org_repo or _FakeOrganizationRepo()
        app.dependency_overrides[get_member_repo] = lambda: member_repo or _FakeMemberRepo()
    else:
        app.dependency_overrides[get_current_organization_context] = (
            lambda: OrganizationContext(organization_id="org-1")
        )

    return app


@pytest.mark.asyncio
async def test_notification_routes_return_scoped_payloads() -> None:
    service = _FakeNotificationService()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        unread_response = await client.get(
            "/api/v1/notifications/unread-count",
            headers={"X-Organization-ID": "org-1"},
        )
        list_response = await client.get(
            "/api/v1/notifications",
            params={"page": 2, "page_size": 1},
            headers={"X-Organization-ID": "org-1"},
        )
        mark_one_response = await client.post(
            "/api/v1/notifications/notif-1/read",
            headers={"X-Organization-ID": "org-1"},
        )
        mark_all_response = await client.post(
            "/api/v1/notifications/read-all",
            headers={"X-Organization-ID": "org-1"},
        )

    assert unread_response.status_code == 200
    assert unread_response.json() == {"unread_count": 2}

    assert list_response.status_code == 200
    payload = list_response.json()
    assert [item["id"] for item in payload["items"]] == ["notif-2", "notif-1"]
    assert payload["page"] == 2
    assert payload["page_size"] == 1

    assert mark_one_response.status_code == 200
    assert mark_one_response.json()["is_read"] is True
    assert mark_all_response.status_code == 200
    assert mark_all_response.json()["updated_count"] == 2

    assert service.unread_calls[0]["organization_id"] == "org-1"
    assert service.list_calls[0]["page"] == 2
    assert service.list_calls[0]["page_size"] == 1
    assert service.mark_one_calls[0]["notification_id"] == "notif-1"
    assert service.mark_all_calls[0]["organization_id"] == "org-1"


@pytest.mark.asyncio
async def test_notification_routes_require_x_organization_id_header() -> None:
    service = _FakeNotificationService()
    app = _build_test_app(service=service, use_real_org_context=True)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/notifications/unread-count")

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Organization-ID header is required"
