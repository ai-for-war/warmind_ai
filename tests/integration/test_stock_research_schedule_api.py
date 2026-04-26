from __future__ import annotations

from datetime import datetime, timezone
import importlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

service_module = importlib.import_module("app.common.service")
if not hasattr(service_module, "get_redis_queue"):
    service_module.get_redis_queue = lambda: None
if not hasattr(service_module, "get_stock_research_schedule_service"):
    service_module.get_stock_research_schedule_service = lambda: None
if not hasattr(service_module, "get_stock_research_schedule_dispatcher_service"):
    service_module.get_stock_research_schedule_dispatcher_service = lambda: None

from app.api.deps import (  # noqa: E402
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.internal import router as internal_router_module  # noqa: E402
from app.api.v1.internal.router import router as internal_router  # noqa: E402
from app.api.v1.stock_research.schedules import (  # noqa: E402
    router as stock_research_schedule_router,
)
from app.common.exceptions import AppException, StockResearchScheduleNotFoundError  # noqa: E402
from app.common.service import (  # noqa: E402
    get_stock_research_schedule_dispatcher_service,
    get_stock_research_schedule_service,
)
from app.domain.models.stock_research_report import (  # noqa: E402
    StockResearchReportStatus,
)
from app.domain.models.stock_research_schedule import (  # noqa: E402
    StockResearchScheduleStatus,
)
from app.domain.models.user import User, UserRole  # noqa: E402
from app.domain.schemas.stock_research_report import (  # noqa: E402
    StockResearchReportCreateResponse,
)
from app.domain.schemas.stock_research_schedule import (  # noqa: E402
    StockResearchScheduleDeleteResponse,
    StockResearchScheduleListResponse,
    StockResearchScheduleResponse,
)


def _utc(year: int = 2026, month: int = 4, day: int = 24, hour: int = 1) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _user(*, user_id: str = "user-1", role: UserRole = UserRole.USER) -> User:
    return User(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        role=role,
        is_active=True,
        created_at=_utc(),
        updated_at=_utc(),
    )


def _runtime_config_payload() -> dict[str, str]:
    return {
        "provider": "openai",
        "model": "gpt-5.2",
        "reasoning": "high",
    }


def _schedule_response(
    *,
    schedule_id: str = "schedule-1",
    symbol: str = "FPT",
    status: StockResearchScheduleStatus = StockResearchScheduleStatus.ACTIVE,
) -> StockResearchScheduleResponse:
    return StockResearchScheduleResponse(
        id=schedule_id,
        symbol=symbol,
        status=status,
        schedule={"type": "daily", "hour": 8, "weekdays": []},
        next_run_at=_utc(2026, 4, 24, 1),
        created_at=_utc(2026, 4, 23, 1),
        updated_at=_utc(2026, 4, 23, 1),
        runtime_config=_runtime_config_payload(),
    )


def _report_create_response() -> StockResearchReportCreateResponse:
    return StockResearchReportCreateResponse(
        id="report-1",
        symbol="FPT",
        status=StockResearchReportStatus.QUEUED,
        created_at=_utc(),
        started_at=None,
        completed_at=None,
        updated_at=_utc(),
        runtime_config=_runtime_config_payload(),
    )


class _FakeStockResearchScheduleService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.raise_not_found = False

    def _record(self, method_name: str, kwargs: dict[str, object]) -> None:
        self.calls.append((method_name, kwargs))

    def _maybe_raise_not_found(self) -> None:
        if self.raise_not_found:
            raise StockResearchScheduleNotFoundError()

    async def create_schedule(self, **kwargs) -> StockResearchScheduleResponse:
        self._record("create_schedule", kwargs)
        return _schedule_response()

    async def list_schedules(self, **kwargs) -> StockResearchScheduleListResponse:
        self._record("list_schedules", kwargs)
        return StockResearchScheduleListResponse(
            items=[_schedule_response(), _schedule_response(schedule_id="schedule-2")],
            total=7,
            page=kwargs.get("page", 1),
            page_size=kwargs.get("page_size", 20),
        )

    async def get_schedule(self, **kwargs) -> StockResearchScheduleResponse:
        self._record("get_schedule", kwargs)
        self._maybe_raise_not_found()
        return _schedule_response(schedule_id=str(kwargs["schedule_id"]))

    async def update_schedule(self, **kwargs) -> StockResearchScheduleResponse:
        self._record("update_schedule", kwargs)
        return _schedule_response(schedule_id=str(kwargs["schedule_id"]), symbol="VCB")

    async def pause_schedule(self, **kwargs) -> StockResearchScheduleResponse:
        self._record("pause_schedule", kwargs)
        return _schedule_response(
            schedule_id=str(kwargs["schedule_id"]),
            status=StockResearchScheduleStatus.PAUSED,
        )

    async def resume_schedule(self, **kwargs) -> StockResearchScheduleResponse:
        self._record("resume_schedule", kwargs)
        return _schedule_response(schedule_id=str(kwargs["schedule_id"]))

    async def delete_schedule(self, **kwargs) -> StockResearchScheduleDeleteResponse:
        self._record("delete_schedule", kwargs)
        return StockResearchScheduleDeleteResponse(
            id=str(kwargs["schedule_id"]),
            deleted=True,
        )

    async def run_now(self, **kwargs) -> StockResearchReportCreateResponse:
        self._record("run_now", kwargs)
        return _report_create_response()


class _FakeDispatcher:
    def __init__(self) -> None:
        self.calls = 0

    async def dispatch_due(self):
        self.calls += 1
        return SimpleNamespace(
            scanned=3,
            dispatched=2,
            skipped=1,
            enqueue_failed=0,
        )


def _build_schedule_app(
    *,
    service: _FakeStockResearchScheduleService,
    org_context: OrganizationContext | None = None,
) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        del request
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    app.include_router(stock_research_schedule_router, prefix="/api/v1")
    app.dependency_overrides[get_stock_research_schedule_service] = lambda: service
    app.dependency_overrides[get_current_active_user] = lambda: _user()
    app.dependency_overrides[get_current_organization_context] = (
        lambda: org_context or OrganizationContext(organization_id="org-1")
    )
    return app


def _build_internal_app(*, dispatcher: _FakeDispatcher) -> FastAPI:
    app = FastAPI()
    app.include_router(internal_router, prefix="/api/v1")
    app.dependency_overrides[get_stock_research_schedule_dispatcher_service] = (
        lambda: dispatcher
    )
    return app


@pytest.mark.asyncio
async def test_schedule_crud_routes_use_user_and_organization_scope() -> None:
    service = _FakeStockResearchScheduleService()
    app = _build_schedule_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        create_response = await client.post(
            "/api/v1/stock-research/schedules",
            json={
                "symbol": "fpt",
                "runtime_config": _runtime_config_payload(),
                "schedule": {"type": "daily", "hour": 8},
            },
        )
        list_response = await client.get(
            "/api/v1/stock-research/schedules",
            params={"page": 2, "page_size": 2},
        )
        get_response = await client.get(
            "/api/v1/stock-research/schedules/schedule-1"
        )
        update_response = await client.patch(
            "/api/v1/stock-research/schedules/schedule-1",
            json={"symbol": "vcb"},
        )
        pause_response = await client.post(
            "/api/v1/stock-research/schedules/schedule-1/pause"
        )
        resume_response = await client.post(
            "/api/v1/stock-research/schedules/schedule-1/resume"
        )
        delete_response = await client.delete(
            "/api/v1/stock-research/schedules/schedule-1"
        )

    assert create_response.status_code == 201
    assert create_response.json()["schedule"] == {
        "type": "daily",
        "hour": 8,
        "weekdays": [],
    }
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload["items"]) == 2
    assert list_payload["total"] == 7
    assert list_payload["page"] == 2
    assert list_payload["page_size"] == 2
    assert get_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["symbol"] == "VCB"
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == "paused"
    assert resume_response.status_code == 200
    assert resume_response.json()["status"] == "active"
    assert delete_response.status_code == 200
    assert delete_response.json() == {"id": "schedule-1", "deleted": True}

    method_names = [method_name for method_name, _ in service.calls]
    assert method_names == [
        "create_schedule",
        "list_schedules",
        "get_schedule",
        "update_schedule",
        "pause_schedule",
        "resume_schedule",
        "delete_schedule",
    ]
    for _, kwargs in service.calls:
        assert kwargs["current_user"].id == "user-1"
        assert kwargs["organization_id"] == "org-1"
    assert service.calls[1][1]["page"] == 2
    assert service.calls[1][1]["page_size"] == 2


@pytest.mark.asyncio
async def test_schedule_get_rejects_schedule_outside_owner_scope() -> None:
    service = _FakeStockResearchScheduleService()
    service.raise_not_found = True
    app = _build_schedule_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/stock-research/schedules/other")

    assert response.status_code == 404
    assert response.json()["detail"] == "Stock research schedule not found"


@pytest.mark.asyncio
async def test_schedule_run_now_returns_accepted_queued_report() -> None:
    service = _FakeStockResearchScheduleService()
    app = _build_schedule_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/stock-research/schedules/schedule-1/run-now"
        )

    assert response.status_code == 202
    assert response.json()["id"] == "report-1"
    assert response.json()["status"] == "queued"
    assert service.calls[-1][0] == "run_now"
    assert service.calls[-1][1]["schedule_id"] == "schedule-1"


@pytest.mark.asyncio
async def test_internal_dispatch_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = _FakeDispatcher()
    app = _build_internal_app(dispatcher=dispatcher)
    monkeypatch.setattr(
        internal_router_module,
        "get_settings",
        lambda: SimpleNamespace(INTERNAL_API_KEY="secret"),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        missing_response = await client.post(
            "/api/v1/internal/trigger-stock-research-schedules"
        )
        invalid_response = await client.post(
            "/api/v1/internal/trigger-stock-research-schedules",
            headers={"X-API-Key": "wrong"},
        )
        accepted_response = await client.post(
            "/api/v1/internal/trigger-stock-research-schedules",
            headers={"X-API-Key": "secret"},
        )

    assert missing_response.status_code == 401
    assert missing_response.json()["detail"] == "Missing API key"
    assert invalid_response.status_code == 401
    assert invalid_response.json()["detail"] == "Invalid API key"
    assert accepted_response.status_code == 200
    assert accepted_response.json()["status"] == "accepted"
    assert "timestamp" in accepted_response.json()
    assert dispatcher.calls == 1
