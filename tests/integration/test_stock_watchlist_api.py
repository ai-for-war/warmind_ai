from __future__ import annotations

import sys
import types

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

if "app.common.service" not in sys.modules:
    fake_common_service = types.ModuleType("app.common.service")

    def _unused_get_auth_service():
        raise AssertionError("get_auth_service should not be used in this test")

    def _unused_get_stock_watchlist_service():
        raise AssertionError(
            "get_stock_watchlist_service should be overridden in this test"
        )

    fake_common_service.get_auth_service = _unused_get_auth_service
    fake_common_service.get_stock_watchlist_service = (
        _unused_get_stock_watchlist_service
    )
    sys.modules["app.common.service"] = fake_common_service

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.stocks.watchlists import router as watchlists_router
from app.common.exceptions import AppException
from app.common.repo import get_member_repo, get_org_repo
from app.common.service import get_stock_watchlist_service
from app.services.stocks.watchlist_service import StockWatchlistService
from tests.support.watchlist_testkit import (
    FakeMemberRepo,
    FakeOrganizationRepo,
    InMemoryStockRepo,
    InMemoryWatchlistItemRepo,
    InMemoryWatchlistRepo,
    build_stock,
    build_user,
)


def _build_test_app(
    *,
    service: StockWatchlistService,
    use_real_org_context: bool = False,
    org_repo: FakeOrganizationRepo | None = None,
    member_repo: FakeMemberRepo | None = None,
) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(_request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.include_router(watchlists_router)
    app.dependency_overrides[get_current_active_user] = lambda: build_user()
    if use_real_org_context:
        app.dependency_overrides[get_org_repo] = lambda: (
            org_repo or FakeOrganizationRepo()
        )
        app.dependency_overrides[get_member_repo] = lambda: (
            member_repo or FakeMemberRepo()
        )
    else:
        app.dependency_overrides[get_current_organization_context] = lambda: (
            OrganizationContext(organization_id="org-1")
        )
    app.dependency_overrides[get_stock_watchlist_service] = lambda: service
    return app


@pytest.mark.asyncio
async def test_watchlist_routes_require_x_organization_id_header() -> None:
    service = StockWatchlistService(
        watchlist_repo=InMemoryWatchlistRepo(),
        item_repo=InMemoryWatchlistItemRepo(),
        stock_repo=InMemoryStockRepo([build_stock(symbol="FPT", organ_name="FPT")]),
    )
    app = _build_test_app(service=service, use_real_org_context=True)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/stocks/watchlists")

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Organization-ID header is required"


@pytest.mark.asyncio
async def test_watchlist_routes_reject_user_without_org_membership() -> None:
    service = StockWatchlistService(
        watchlist_repo=InMemoryWatchlistRepo(),
        item_repo=InMemoryWatchlistItemRepo(),
        stock_repo=InMemoryStockRepo([build_stock(symbol="FPT", organ_name="FPT")]),
    )
    app = _build_test_app(
        service=service,
        use_real_org_context=True,
        member_repo=FakeMemberRepo(memberships=set()),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/stocks/watchlists",
            headers={"X-Organization-ID": "org-1"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


@pytest.mark.asyncio
async def test_watchlist_api_supports_full_crud_and_item_flows() -> None:
    service = StockWatchlistService(
        watchlist_repo=InMemoryWatchlistRepo(),
        item_repo=InMemoryWatchlistItemRepo(),
        stock_repo=InMemoryStockRepo(
            [
                build_stock(
                    symbol="FPT",
                    organ_name="Cong ty Co phan FPT",
                    exchange="HOSE",
                    groups=["VN30"],
                    industry_code=8300,
                    industry_name="Cong nghe",
                ),
                build_stock(
                    symbol="VCB",
                    organ_name="Ngan hang Vietcombank",
                    exchange="HOSE",
                    groups=["VN30"],
                    industry_code=8300,
                    industry_name="Tai chinh",
                ),
            ]
        ),
    )
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        create_response = await client.post(
            "/stocks/watchlists",
            json={"name": "Tech"},
        )
        assert create_response.status_code == 201
        watchlist = create_response.json()

        second_watchlist_response = await client.post(
            "/stocks/watchlists",
            json={"name": "Banks"},
        )
        assert second_watchlist_response.status_code == 201
        second_watchlist = second_watchlist_response.json()

        rename_response = await client.patch(
            f"/stocks/watchlists/{watchlist['id']}",
            json={"name": "Growth"},
        )
        assert rename_response.status_code == 200
        assert rename_response.json()["name"] == "Growth"

        add_fpt_response = await client.post(
            f"/stocks/watchlists/{watchlist['id']}/items",
            json={"symbol": "fpt"},
        )
        assert add_fpt_response.status_code == 201
        assert add_fpt_response.json()["symbol"] == "FPT"

        add_vcb_response = await client.post(
            f"/stocks/watchlists/{watchlist['id']}/items",
            json={"symbol": "VCB"},
        )
        assert add_vcb_response.status_code == 201

        add_same_symbol_other_watchlist = await client.post(
            f"/stocks/watchlists/{second_watchlist['id']}/items",
            json={"symbol": "FPT"},
        )
        assert add_same_symbol_other_watchlist.status_code == 201

        list_watchlists_response = await client.get("/stocks/watchlists")
        assert list_watchlists_response.status_code == 200
        assert len(list_watchlists_response.json()["items"]) == 2

        list_items_response = await client.get(
            f"/stocks/watchlists/{watchlist['id']}/items"
        )
        assert list_items_response.status_code == 200
        items_body = list_items_response.json()
        assert items_body["watchlist"]["id"] == watchlist["id"]
        assert [item["symbol"] for item in items_body["items"]] == ["VCB", "FPT"]
        assert items_body["items"][0]["stock"]["exchange"] == "HOSE"
        assert items_body["items"][1]["stock"]["organ_name"] == "Cong ty Co phan FPT"

        remove_item_response = await client.delete(
            f"/stocks/watchlists/{watchlist['id']}/items/FPT"
        )
        assert remove_item_response.status_code == 200
        assert remove_item_response.json()["removed"] is True

        delete_watchlist_response = await client.delete(
            f"/stocks/watchlists/{watchlist['id']}"
        )
        assert delete_watchlist_response.status_code == 200
        assert delete_watchlist_response.json()["deleted"] is True

        remaining_watchlists_response = await client.get("/stocks/watchlists")
        assert remaining_watchlists_response.status_code == 200
        remaining_ids = {
            item["id"] for item in remaining_watchlists_response.json()["items"]
        }
        assert remaining_ids == {second_watchlist["id"]}

        deleted_items_response = await client.get(
            f"/stocks/watchlists/{watchlist['id']}/items"
        )
        assert deleted_items_response.status_code == 404


@pytest.mark.asyncio
async def test_watchlist_api_returns_conflicts_for_duplicate_name_and_symbol() -> None:
    service = StockWatchlistService(
        watchlist_repo=InMemoryWatchlistRepo(),
        item_repo=InMemoryWatchlistItemRepo(),
        stock_repo=InMemoryStockRepo([build_stock(symbol="FPT", organ_name="FPT")]),
    )
    app = _build_test_app(service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first_watchlist_response = await client.post(
            "/stocks/watchlists",
            json={"name": "Tech"},
        )
        assert first_watchlist_response.status_code == 201
        watchlist_id = first_watchlist_response.json()["id"]

        duplicate_name_response = await client.post(
            "/stocks/watchlists",
            json={"name": "tech"},
        )
        assert duplicate_name_response.status_code == 409
        assert duplicate_name_response.json()["detail"] == "Stock watchlist name already exists"

        first_item_response = await client.post(
            f"/stocks/watchlists/{watchlist_id}/items",
            json={"symbol": "FPT"},
        )
        assert first_item_response.status_code == 201

        duplicate_item_response = await client.post(
            f"/stocks/watchlists/{watchlist_id}/items",
            json={"symbol": "fpt"},
        )

    assert duplicate_item_response.status_code == 409
    assert (
        duplicate_item_response.json()["detail"]
        == "Stock symbol already exists in this watchlist"
    )
