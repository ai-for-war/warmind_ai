from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.stocks.router import router as stocks_router
from app.common.repo import get_member_repo, get_org_repo
from app.common.service import get_stock_financial_report_service
from app.domain.models.user import User, UserRole
from app.domain.schemas.stock_financial_report import StockFinancialReportResponse


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _user(*, user_id: str = "user-1", role: UserRole = UserRole.USER) -> User:
    now = _utc(2026, 1, 1)
    return User(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


class _FakeFinancialReportService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def get_report(
        self,
        symbol: str,
        report_type,
        query,
    ) -> StockFinancialReportResponse:
        self.calls.append((symbol, report_type.value, query.period))
        return StockFinancialReportResponse(
            symbol=symbol,
            source="KBS",
            report_type=report_type,
            period=query.period,
            periods=["2025-Q4", "2025-Q3"],
            cache_hit=False,
            items=[
                {
                    "item": "Revenue",
                    "item_id": "revenue",
                    "values": {"2025-Q4": 1000, "2025-Q3": 900},
                }
            ],
        )


class _FakeOrganization:
    def __init__(self, *, is_active: bool = True) -> None:
        self.is_active = is_active


class _FakeOrganizationRepo:
    async def find_by_id(self, organization_id: str):
        if organization_id == "org-1":
            return _FakeOrganization(is_active=True)
        return None


class _FakeMembership:
    role = "member"


class _FakeMemberRepo:
    async def find_by_user_and_org(
        self,
        *,
        user_id: str,
        organization_id: str,
        is_active: bool,
    ):
        del is_active
        if user_id == "user-1" and organization_id == "org-1":
            return _FakeMembership()
        return None


def _build_test_app(
    *,
    service: _FakeFinancialReportService,
    use_real_org_context: bool = False,
    member_repo: _FakeMemberRepo | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(stocks_router)
    app.dependency_overrides[get_current_active_user] = lambda: _user()
    if use_real_org_context:
        app.dependency_overrides[get_org_repo] = lambda: _FakeOrganizationRepo()
        app.dependency_overrides[get_member_repo] = lambda: (
            member_repo or _FakeMemberRepo()
        )
    else:
        app.dependency_overrides[get_current_organization_context] = lambda: (
            OrganizationContext(organization_id="org-1")
        )
    app.dependency_overrides[get_stock_financial_report_service] = lambda: service
    return app


@pytest.mark.asyncio
async def test_financial_report_route_returns_normalized_response_shape() -> None:
    service = _FakeFinancialReportService()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/FPT/financial-reports/income-statement",
            params={"period": "year"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "symbol": "FPT",
        "source": "KBS",
        "report_type": "income-statement",
        "period": "year",
        "periods": ["2025-Q4", "2025-Q3"],
        "cache_hit": False,
        "items": [
            {
                "item": "Revenue",
                "item_id": "revenue",
                "values": {"2025-Q4": 1000, "2025-Q3": 900},
            }
        ],
    }
    assert service.calls == [("FPT", "income-statement", "year")]


@pytest.mark.asyncio
async def test_financial_report_route_defaults_period_to_quarter() -> None:
    service = _FakeFinancialReportService()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/stocks/FPT/financial-reports/ratio")

    assert response.status_code == 200
    assert service.calls == [("FPT", "ratio", "quarter")]


@pytest.mark.asyncio
async def test_financial_report_route_rejects_unsupported_report_type() -> None:
    service = _FakeFinancialReportService()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/stocks/FPT/financial-reports/overview")

    assert response.status_code == 422
    assert service.calls == []


@pytest.mark.asyncio
async def test_financial_report_route_rejects_unsupported_period() -> None:
    service = _FakeFinancialReportService()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/FPT/financial-reports/ratio",
            params={"period": "month"},
        )

    assert response.status_code == 422
    assert service.calls == []


@pytest.mark.asyncio
async def test_financial_report_route_requires_x_organization_id_header() -> None:
    service = _FakeFinancialReportService()
    app = _build_test_app(service=service, use_real_org_context=True)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/stocks/FPT/financial-reports/ratio")

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Organization-ID header is required"
    assert service.calls == []


@pytest.mark.asyncio
async def test_financial_report_route_rejects_user_without_org_membership() -> None:
    service = _FakeFinancialReportService()

    class _DenyMemberRepo(_FakeMemberRepo):
        async def find_by_user_and_org(self, **kwargs):
            del kwargs
            return None

    app = _build_test_app(
        service=service,
        use_real_org_context=True,
        member_repo=_DenyMemberRepo(),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/FPT/financial-reports/ratio",
            headers={"X-Organization-ID": "org-1"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"
    assert service.calls == []


@pytest.mark.asyncio
async def test_financial_report_route_surfaces_not_found_from_service() -> None:
    service = _FakeFinancialReportService()

    async def _missing_report(_symbol: str, _report_type, _query):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Financial report data not found",
        )

    service.get_report = _missing_report  # type: ignore[method-assign]
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/stocks/FPT/financial-reports/cash-flow")

    assert response.status_code == 404
    assert response.json()["detail"] == "Financial report data not found"


@pytest.mark.asyncio
async def test_financial_reports_do_not_have_aggregate_route() -> None:
    service = _FakeFinancialReportService()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/stocks/FPT/financial-reports")

    assert response.status_code == 404
    assert service.calls == []
