from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
    require_super_admin,
)
from app.api.v1.stocks.router import router as stocks_router
from app.common.exceptions import AppException
from app.common.service import get_stock_catalog_service, get_stock_company_service
from app.domain.models.user import User, UserRole
from app.domain.schemas.stock import StockListItem, StockListResponse, StockRefreshResponse
from app.domain.schemas.stock_company import (
    StockCompanyOfficersResponse,
    StockCompanyOverviewResponse,
)


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


class _FakeStockCatalogService:
    def __init__(self) -> None:
        self.list_calls = []
        self.refresh_calls = 0

    async def list_stocks(self, query) -> StockListResponse:
        self.list_calls.append(query)
        return StockListResponse(
            items=[
                StockListItem(
                    symbol="FPT",
                    organ_name="Cong ty Co phan FPT",
                    exchange="HOSE",
                    groups=["VN30"],
                    industry_code=8300,
                    industry_name="Cong nghe",
                    source="VCI",
                    snapshot_at=_utc(2026, 4, 12),
                    updated_at=_utc(2026, 4, 12, 1),
                )
            ],
            total=1,
            page=query.page,
            page_size=query.page_size,
        )

    async def refresh_catalog(self) -> StockRefreshResponse:
        self.refresh_calls += 1
        return StockRefreshResponse(
            status="success",
            source="VCI",
            upserted=1,
            updated_at=_utc(2026, 4, 12),
        )


class _FakeStockCompanyService:
    def __init__(self) -> None:
        self.overview_calls: list[str] = []
        self.officers_calls: list[tuple[str, str]] = []

    async def get_overview(self, symbol: str) -> StockCompanyOverviewResponse:
        self.overview_calls.append(symbol)
        return StockCompanyOverviewResponse(
            symbol=symbol,
            source="VCI",
            fetched_at=_utc(2026, 4, 13),
            cache_hit=False,
            item={
                "symbol": symbol,
                "company_profile": "Cong ty Co phan FPT",
            },
        )

    async def get_officers(
        self,
        symbol: str,
        *,
        filter_by: str = "working",
    ) -> StockCompanyOfficersResponse:
        self.officers_calls.append((symbol, filter_by))
        return StockCompanyOfficersResponse(
            symbol=symbol,
            source="VCI",
            fetched_at=_utc(2026, 4, 13),
            cache_hit=True,
            items=[
                {
                    "id": 1,
                    "officer_name": "CEO",
                }
            ],
        )


def _build_test_app(
    *,
    service: _FakeStockCatalogService,
    company_service: _FakeStockCompanyService | None = None,
) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(_request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.include_router(stocks_router)
    app.dependency_overrides[get_current_active_user] = lambda: _user()
    app.dependency_overrides[get_current_organization_context] = (
        lambda: OrganizationContext(organization_id="org-1")
    )
    app.dependency_overrides[get_stock_catalog_service] = lambda: service
    if company_service is not None:
        app.dependency_overrides[get_stock_company_service] = lambda: company_service
    return app


@pytest.mark.asyncio
async def test_list_stocks_requires_org_auth_dependencies_and_returns_response() -> None:
    service = _FakeStockCatalogService()
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks",
            params={"q": "fpt", "exchange": "hose", "group": "vn30"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["symbol"] == "FPT"
    assert service.list_calls[0].q == "fpt"
    assert service.list_calls[0].exchange == "HOSE"
    assert service.list_calls[0].group == "VN30"


@pytest.mark.asyncio
async def test_refresh_stock_catalog_requires_super_admin() -> None:
    service = _FakeStockCatalogService()
    app = _build_test_app(service=service)

    async def _deny_refresh():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )

    app.dependency_overrides[require_super_admin] = _deny_refresh

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/stocks/refresh")

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


@pytest.mark.asyncio
async def test_refresh_stock_catalog_allows_super_admin() -> None:
    service = _FakeStockCatalogService()
    app = _build_test_app(service=service)
    app.dependency_overrides[require_super_admin] = lambda: _user(
        user_id="admin-1",
        role=UserRole.SUPER_ADMIN,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/stocks/refresh")

    assert response.status_code == 200
    assert response.json()["upserted"] == 1
    assert service.refresh_calls == 1


@pytest.mark.asyncio
async def test_get_stock_company_overview_requires_org_auth_and_returns_metadata() -> None:
    service = _FakeStockCatalogService()
    company_service = _FakeStockCompanyService()
    app = _build_test_app(service=service, company_service=company_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/stocks/FPT/company/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "FPT"
    assert body["source"] == "VCI"
    assert body["cache_hit"] is False
    assert body["item"]["company_profile"] == "Cong ty Co phan FPT"
    assert company_service.overview_calls == ["FPT"]


@pytest.mark.asyncio
async def test_get_stock_company_officers_passes_filter_query() -> None:
    service = _FakeStockCatalogService()
    company_service = _FakeStockCompanyService()
    app = _build_test_app(service=service, company_service=company_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/FPT/company/officers",
            params={"filter_by": "resigned"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_hit"] is True
    assert body["items"][0]["officer_name"] == "CEO"
    assert company_service.officers_calls == [("FPT", "resigned")]


@pytest.mark.asyncio
async def test_get_stock_company_overview_surfaces_not_found_from_service() -> None:
    service = _FakeStockCatalogService()
    app = _build_test_app(service=service)

    async def _missing_company(_symbol: str):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stock symbol not found",
        )

    company_service = _FakeStockCompanyService()
    company_service.get_overview = _missing_company  # type: ignore[method-assign]
    app.dependency_overrides[get_stock_company_service] = lambda: company_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/stocks/UNKNOWN/company/overview")

    assert response.status_code == 404
    assert response.json()["detail"] == "Stock symbol not found"
