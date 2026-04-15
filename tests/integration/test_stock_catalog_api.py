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
from app.common.repo import get_member_repo, get_org_repo
from app.common.service import (
    get_stock_catalog_service,
    get_stock_company_service,
    get_stock_price_service,
)
from app.domain.models.user import User, UserRole
from app.domain.schemas.stock import (
    StockListItem,
    StockListResponse,
    StockRefreshResponse,
)
from app.domain.schemas.stock_company import (
    StockCompanyNewsResponse,
    StockCompanyOfficersResponse,
    StockCompanyOverviewResponse,
    StockCompanySubsidiariesResponse,
)
from app.domain.schemas.stock_price import (
    StockPriceHistoryResponse,
    StockPriceIntradayResponse,
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
        self.subsidiaries_calls: list[tuple[str, str]] = []
        self.news_calls: list[str] = []

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

    async def get_subsidiaries(
        self,
        symbol: str,
        *,
        filter_by: str = "all",
    ) -> StockCompanySubsidiariesResponse:
        self.subsidiaries_calls.append((symbol, filter_by))
        return StockCompanySubsidiariesResponse(
            symbol=symbol,
            source="VCI",
            fetched_at=_utc(2026, 4, 13),
            cache_hit=False,
            items=[
                {
                    "id": 2,
                    "organ_name": "FPT Software",
                    "type": "cong ty con",
                }
            ],
        )

    async def get_news(self, symbol: str) -> StockCompanyNewsResponse:
        self.news_calls.append(symbol)
        return StockCompanyNewsResponse(
            symbol=symbol,
            source="VCI",
            fetched_at=_utc(2026, 4, 13),
            cache_hit=False,
            items=[
                {
                    "id": 3,
                    "news_title": "FPT expands",
                }
            ],
        )


class _FakeStockPriceService:
    def __init__(self) -> None:
        self.history_calls: list[tuple[str, object]] = []
        self.intraday_calls: list[tuple[str, object]] = []

    async def get_history(self, symbol: str, query) -> StockPriceHistoryResponse:
        self.history_calls.append((symbol, query))
        return StockPriceHistoryResponse(
            symbol=symbol,
            source="VCI",
            cache_hit=False,
            interval=query.interval,
            items=[
                {
                    "time": "2026-04-15",
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 101.0,
                    "volume": 1000,
                }
            ],
        )

    async def get_intraday(self, symbol: str, query) -> StockPriceIntradayResponse:
        self.intraday_calls.append((symbol, query))
        return StockPriceIntradayResponse(
            symbol=symbol,
            source="VCI",
            cache_hit=True,
            items=[
                {
                    "time": "2026-04-15T09:15:00",
                    "price": 101.2,
                    "volume": 50,
                    "match_type": "Buy",
                    "id": 42,
                }
            ],
        )


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
    service: _FakeStockCatalogService,
    company_service: _FakeStockCompanyService | None = None,
    price_service: _FakeStockPriceService | None = None,
    use_real_org_context: bool = False,
    org_repo: _FakeOrganizationRepo | None = None,
    member_repo: _FakeMemberRepo | None = None,
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
    if use_real_org_context:
        app.dependency_overrides[get_org_repo] = lambda: (
            org_repo or _FakeOrganizationRepo()
        )
        app.dependency_overrides[get_member_repo] = lambda: (
            member_repo or _FakeMemberRepo()
        )
    else:
        app.dependency_overrides[get_current_organization_context] = lambda: (
            OrganizationContext(organization_id="org-1")
        )
    app.dependency_overrides[get_stock_catalog_service] = lambda: service
    if company_service is not None:
        app.dependency_overrides[get_stock_company_service] = lambda: company_service
    if price_service is not None:
        app.dependency_overrides[get_stock_price_service] = lambda: price_service
    return app


@pytest.mark.asyncio
async def test_list_stocks_requires_org_auth_dependencies_and_returns_response() -> (
    None
):
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
async def test_get_stock_company_overview_requires_org_auth_and_returns_metadata() -> (
    None
):
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
async def test_get_stock_company_subsidiaries_passes_filter_query() -> None:
    service = _FakeStockCatalogService()
    company_service = _FakeStockCompanyService()
    app = _build_test_app(service=service, company_service=company_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/FPT/company/subsidiaries",
            params={"filter_by": "subsidiary"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_hit"] is False
    assert body["items"][0]["organ_name"] == "FPT Software"
    assert company_service.subsidiaries_calls == [("FPT", "subsidiary")]


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/stocks/FPT/company/overview",
        "/stocks/FPT/company/shareholders",
        "/stocks/FPT/company/officers",
        "/stocks/FPT/company/subsidiaries",
        "/stocks/FPT/company/affiliate",
        "/stocks/FPT/company/events",
        "/stocks/FPT/company/news",
        "/stocks/FPT/company/reports",
        "/stocks/FPT/company/ratio-summary",
        "/stocks/FPT/company/trading-stats",
    ],
)
async def test_company_routes_require_x_organization_id_header(path: str) -> None:
    service = _FakeStockCatalogService()
    company_service = _FakeStockCompanyService()
    app = _build_test_app(
        service=service,
        company_service=company_service,
        use_real_org_context=True,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Organization-ID header is required"


@pytest.mark.asyncio
async def test_company_route_rejects_user_without_org_membership() -> None:
    service = _FakeStockCatalogService()
    company_service = _FakeStockCompanyService()
    app = _build_test_app(
        service=service,
        company_service=company_service,
        use_real_org_context=True,
        member_repo=_FakeMemberRepo(memberships=set()),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/FPT/company/overview",
            headers={"X-Organization-ID": "org-1"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


@pytest.mark.asyncio
async def test_one_failing_company_endpoint_does_not_block_other_endpoints() -> None:
    service = _FakeStockCatalogService()
    company_service = _FakeStockCompanyService()
    app = _build_test_app(service=service, company_service=company_service)

    async def _failing_overview(_symbol: str):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="overview failed",
        )

    company_service.get_overview = _failing_overview  # type: ignore[method-assign]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        overview_response = await client.get("/stocks/FPT/company/overview")
        news_response = await client.get("/stocks/FPT/company/news")

    assert overview_response.status_code == 500
    assert overview_response.json()["detail"] == "overview failed"
    assert news_response.status_code == 200
    assert news_response.json()["items"][0]["news_title"] == "FPT expands"
    assert company_service.news_calls == ["FPT"]


@pytest.mark.asyncio
async def test_get_stock_price_history_requires_org_auth_and_returns_metadata() -> None:
    service = _FakeStockCatalogService()
    price_service = _FakeStockPriceService()
    app = _build_test_app(service=service, price_service=price_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/FPT/prices/history",
            params={"start": "2026-04-01", "interval": "1D"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "FPT"
    assert body["source"] == "VCI"
    assert body["cache_hit"] is False
    assert body["interval"] == "1D"
    assert body["items"][0]["close"] == 101.0
    assert price_service.history_calls[0][0] == "FPT"
    assert price_service.history_calls[0][1].start == "2026-04-01"


@pytest.mark.asyncio
async def test_get_stock_price_intraday_passes_query_params() -> None:
    service = _FakeStockCatalogService()
    price_service = _FakeStockPriceService()
    app = _build_test_app(service=service, price_service=price_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/FPT/prices/intraday",
            params={
                "page_size": 120,
                "last_time": "2026-04-15 09:15:00",
                "last_time_format": "%Y-%m-%d %H:%M:%S",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_hit"] is True
    assert body["items"][0]["id"] == 42
    assert price_service.intraday_calls[0][0] == "FPT"
    assert price_service.intraday_calls[0][1].page_size == 120
    assert price_service.intraday_calls[0][1].last_time == "2026-04-15 09:15:00"


@pytest.mark.asyncio
async def test_get_stock_price_history_surfaces_not_found_from_service() -> None:
    service = _FakeStockCatalogService()
    app = _build_test_app(service=service)

    async def _missing_history(_symbol: str, _query):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stock symbol not found",
        )

    price_service = _FakeStockPriceService()
    price_service.get_history = _missing_history  # type: ignore[method-assign]
    app.dependency_overrides[get_stock_price_service] = lambda: price_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/UNKNOWN/prices/history",
            params={"start": "2026-04-01"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Stock symbol not found"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/stocks/FPT/prices/history?start=2026-04-01",
        "/stocks/FPT/prices/intraday",
    ],
)
async def test_price_routes_require_x_organization_id_header(path: str) -> None:
    service = _FakeStockCatalogService()
    price_service = _FakeStockPriceService()
    app = _build_test_app(
        service=service,
        price_service=price_service,
        use_real_org_context=True,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Organization-ID header is required"


@pytest.mark.asyncio
async def test_price_route_rejects_user_without_org_membership() -> None:
    service = _FakeStockCatalogService()
    price_service = _FakeStockPriceService()
    app = _build_test_app(
        service=service,
        price_service=price_service,
        use_real_org_context=True,
        member_repo=_FakeMemberRepo(memberships=set()),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/FPT/prices/history",
            params={"start": "2026-04-01"},
            headers={"X-Organization-ID": "org-1"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


@pytest.mark.asyncio
async def test_one_failing_price_endpoint_does_not_block_other_price_endpoints() -> (
    None
):
    service = _FakeStockCatalogService()
    price_service = _FakeStockPriceService()
    app = _build_test_app(service=service, price_service=price_service)

    async def _failing_history(_symbol: str, _query):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="history failed",
        )

    price_service.get_history = _failing_history  # type: ignore[method-assign]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        history_response = await client.get(
            "/stocks/FPT/prices/history",
            params={"start": "2026-04-01"},
        )
        intraday_response = await client.get("/stocks/FPT/prices/intraday")

    assert history_response.status_code == 502
    assert history_response.json()["detail"] == "history failed"
    assert intraday_response.status_code == 200
    assert intraday_response.json()["items"][0]["match_type"] == "Buy"
