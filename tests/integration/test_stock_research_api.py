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
service_module.get_stock_research_service = lambda: None
sys.modules.setdefault("app.common.service", service_module)

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.stock_research.router import router as stock_research_router
from app.common.exceptions import AppException, StockSymbolNotFoundError
from app.common.repo import get_member_repo, get_org_repo
from app.common.service import get_stock_research_service
from app.domain.models.stock_research_report import StockResearchReportStatus
from app.domain.models.user import User, UserRole
from app.domain.schemas.stock_research_report import (
    StockResearchReportCreateResponse,
    StockResearchReportListResponse,
    StockResearchReportResponse,
    StockResearchReportSummary,
)


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _user(*, user_id: str = "user-1", role: UserRole = UserRole.USER) -> User:
    now = _utc(2026, 4, 22, 8)
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
    report_id: str = "report-1",
    symbol: str = "FPT",
    status: StockResearchReportStatus = StockResearchReportStatus.QUEUED,
) -> StockResearchReportSummary:
    now = _utc(2026, 4, 22, 8)
    return StockResearchReportSummary(
        id=report_id,
        symbol=symbol,
        status=status,
        created_at=now,
        started_at=None,
        completed_at=None,
        updated_at=now,
    )


class _FakeStockResearchService:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.process_calls: list[dict[str, object]] = []
        self.get_calls: list[dict[str, object]] = []
        self.list_calls: list[dict[str, object]] = []
        self.raise_on_create: Exception | None = None
        self.create_response = StockResearchReportCreateResponse(
            **_summary(report_id="report-1", symbol="FPT").model_dump()
        )
        self.get_response = StockResearchReportResponse(
            **_summary(
                report_id="report-1",
                symbol="FPT",
                status=StockResearchReportStatus.COMPLETED,
            ).model_dump(),
            content="Current price is around 95,800 VND.\n\nEvidence [S1].",
            sources=[
                {
                    "source_id": "S1",
                    "url": "https://example.com/fpt",
                    "title": "FPT Source",
                }
            ],
            error=None,
        )
        self.list_response = StockResearchReportListResponse(
            items=[
                _summary(report_id="report-2", symbol="VCB"),
                _summary(report_id="report-1", symbol="FPT"),
            ]
        )

    async def create_report_request(self, **kwargs) -> StockResearchReportCreateResponse:
        self.create_calls.append(kwargs)
        if self.raise_on_create is not None:
            raise self.raise_on_create
        return self.create_response

    def resolve_request_runtime_config(self, request):
        runtime_config = getattr(request, "runtime_config", None)
        if runtime_config is None:
            return None
        return {
            "provider": runtime_config.provider,
            "model": runtime_config.model,
            "reasoning": runtime_config.reasoning,
        }

    async def process_report(self, **kwargs) -> None:
        self.process_calls.append(kwargs)

    async def get_report(self, **kwargs) -> StockResearchReportResponse:
        self.get_calls.append(kwargs)
        return self.get_response

    async def list_reports(self, **kwargs) -> StockResearchReportListResponse:
        self.list_calls.append(kwargs)
        return self.list_response


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
    service: _FakeStockResearchService,
    use_real_org_context: bool = False,
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

    app.include_router(stock_research_router, prefix="/api/v1")
    app.dependency_overrides[get_stock_research_service] = lambda: service
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
async def test_create_report_returns_202_and_schedules_background_processing() -> None:
    service = _FakeStockResearchService()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/stock-research/reports",
            json={"symbol": "fpt"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["id"] == "report-1"
    assert body["symbol"] == "FPT"
    assert service.create_calls[0]["organization_id"] == "org-1"
    assert service.process_calls == [
        {
            "report_id": "report-1",
            "symbol": "FPT",
            "runtime_config": None,
        }
    ]


@pytest.mark.asyncio
async def test_create_report_surfaces_unknown_symbol_rejection() -> None:
    service = _FakeStockResearchService()
    service.raise_on_create = StockSymbolNotFoundError()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/stock-research/reports",
            json={"symbol": "unknown"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Stock symbol not found"


@pytest.mark.asyncio
async def test_get_and_list_routes_return_owned_reports() -> None:
    service = _FakeStockResearchService()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        get_response = await client.get("/api/v1/stock-research/reports/report-1")
        list_response = await client.get(
            "/api/v1/stock-research/reports",
            params={"symbol": "fpt"},
        )

    assert get_response.status_code == 200
    assert get_response.json()["content"].startswith("Current price is around")
    assert list_response.status_code == 200
    assert [item["symbol"] for item in list_response.json()["items"]] == ["VCB", "FPT"]
    assert service.get_calls[0]["report_id"] == "report-1"
    assert service.list_calls[0]["symbol"] == "fpt"


@pytest.mark.asyncio
async def test_create_route_requires_x_organization_id_header_when_real_org_auth_is_used() -> None:
    service = _FakeStockResearchService()
    app = _build_test_app(service=service, use_real_org_context=True)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/stock-research/reports",
            json={"symbol": "FPT"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Organization-ID header is required"


@pytest.mark.asyncio
async def test_list_route_rejects_user_without_org_membership() -> None:
    service = _FakeStockResearchService()
    app = _build_test_app(
        service=service,
        use_real_org_context=True,
        member_repo=_FakeMemberRepo(memberships=set()),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/stock-research/reports",
            headers={"X-Organization-ID": "org-1"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
