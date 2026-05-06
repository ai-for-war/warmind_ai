from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.sandbox_trade_agent.router import router as sandbox_trade_router
from app.common.exceptions import AppException, SandboxTradeSessionNotFoundError
from app.common.service import get_sandbox_trade_agent_session_service
from app.domain.models.sandbox_trade_agent import (
    SandboxTradeOrderSide,
    SandboxTradeOrderStatus,
    SandboxTradeSessionStatus,
    SandboxTradeSettlementAssetType,
    SandboxTradeSettlementStatus,
    SandboxTradeTickStatus,
)
from app.domain.models.user import User
from app.domain.schemas.sandbox_trade_agent import (
    SandboxTradeOrderListResponse,
    SandboxTradeOrderResponse,
    SandboxTradePortfolioSnapshotListResponse,
    SandboxTradePortfolioSnapshotResponse,
    SandboxTradePortfolioStateResponse,
    SandboxTradePositionResponse,
    SandboxTradeSessionDeleteResponse,
    SandboxTradeSessionLifecycleResponse,
    SandboxTradeSessionListResponse,
    SandboxTradeSessionResponse,
    SandboxTradeSettlementListResponse,
    SandboxTradeSettlementResponse,
    SandboxTradeTickListResponse,
    SandboxTradeTickResponse,
)


def _utc(
    year: int = 2026,
    month: int = 5,
    day: int = 4,
    hour: int = 2,
) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _user() -> User:
    return User(
        _id="user-1",
        email="user@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=_utc(),
        updated_at=_utc(),
    )


def _session_response(
    *,
    session_id: str = "session-1",
    status: SandboxTradeSessionStatus = SandboxTradeSessionStatus.ACTIVE,
) -> SandboxTradeSessionResponse:
    return SandboxTradeSessionResponse(
        id=session_id,
        symbol="FPT",
        status=status,
        initial_capital=100_000_000,
        next_run_at=_utc(),
        created_at=_utc(),
        updated_at=_utc(),
    )


def _tick_response() -> SandboxTradeTickResponse:
    return SandboxTradeTickResponse(
        id="tick-1",
        session_id="session-1",
        tick_at=_utc(),
        status=SandboxTradeTickStatus.COMPLETED,
        created_at=_utc(),
        updated_at=_utc(),
    )


def _order_response() -> SandboxTradeOrderResponse:
    return SandboxTradeOrderResponse(
        id="order-1",
        session_id="session-1",
        tick_id="tick-1",
        symbol="FPT",
        side=SandboxTradeOrderSide.BUY,
        status=SandboxTradeOrderStatus.FILLED,
        quantity=10,
        price=100_000,
        gross_amount=1_000_000,
        filled_at=_utc(),
        trade_date="2026-05-04",
        created_at=_utc(),
        updated_at=_utc(),
    )


def _settlement_response() -> SandboxTradeSettlementResponse:
    return SandboxTradeSettlementResponse(
        id="settlement-1",
        session_id="session-1",
        order_id="order-1",
        symbol="FPT",
        asset_type=SandboxTradeSettlementAssetType.SECURITY,
        status=SandboxTradeSettlementStatus.PENDING,
        quantity=10,
        trade_date="2026-05-04",
        settle_at=_utc(2026, 5, 6, 17),
        created_at=_utc(),
        updated_at=_utc(),
    )


def _position_response() -> SandboxTradePositionResponse:
    return SandboxTradePositionResponse(
        session_id="session-1",
        symbol="FPT",
        available_cash=99_000_000,
        pending_cash=0,
        total_quantity=10,
        sellable_quantity=0,
        pending_quantity=10,
        average_cost=100_000,
        realized_pnl=0,
        created_at=_utc(),
        updated_at=_utc(),
    )


def _snapshot_response() -> SandboxTradePortfolioSnapshotResponse:
    return SandboxTradePortfolioSnapshotResponse(
        id="snapshot-1",
        session_id="session-1",
        tick_id="tick-1",
        symbol="FPT",
        available_cash=99_000_000,
        pending_cash=0,
        total_quantity=10,
        sellable_quantity=0,
        pending_quantity=10,
        latest_price=100_000,
        market_value=1_000_000,
        equity=100_000_000,
        realized_pnl=0,
        unrealized_pnl=0,
        created_at=_utc(),
    )


class _FakeSandboxTradeAgentService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.raise_not_found = False

    def _record(self, method_name: str, kwargs: dict[str, object]) -> None:
        self.calls.append((method_name, kwargs))

    def _maybe_raise_not_found(self) -> None:
        if self.raise_not_found:
            raise SandboxTradeSessionNotFoundError()

    async def create_session(self, **kwargs) -> SandboxTradeSessionResponse:
        self._record("create_session", kwargs)
        return _session_response()

    async def list_sessions(self, **kwargs) -> SandboxTradeSessionListResponse:
        self._record("list_sessions", kwargs)
        return SandboxTradeSessionListResponse(
            items=[_session_response(), _session_response(session_id="session-2")],
            total=7,
            page=kwargs.get("page", 1),
            page_size=kwargs.get("page_size", 20),
        )

    async def get_session(self, **kwargs) -> SandboxTradeSessionResponse:
        self._record("get_session", kwargs)
        self._maybe_raise_not_found()
        return _session_response(session_id=str(kwargs["session_id"]))

    async def update_session(self, **kwargs) -> SandboxTradeSessionResponse:
        self._record("update_session", kwargs)
        return _session_response(session_id=str(kwargs["session_id"]))

    async def pause_session(self, **kwargs) -> SandboxTradeSessionLifecycleResponse:
        self._record("pause_session", kwargs)
        return SandboxTradeSessionLifecycleResponse(
            id=str(kwargs["session_id"]),
            status=SandboxTradeSessionStatus.PAUSED,
            updated_at=_utc(),
        )

    async def resume_session(self, **kwargs) -> SandboxTradeSessionLifecycleResponse:
        self._record("resume_session", kwargs)
        return SandboxTradeSessionLifecycleResponse(
            id=str(kwargs["session_id"]),
            status=SandboxTradeSessionStatus.ACTIVE,
            updated_at=_utc(),
        )

    async def stop_session(self, **kwargs) -> SandboxTradeSessionLifecycleResponse:
        self._record("stop_session", kwargs)
        return SandboxTradeSessionLifecycleResponse(
            id=str(kwargs["session_id"]),
            status=SandboxTradeSessionStatus.STOPPED,
            updated_at=_utc(),
        )

    async def delete_session(self, **kwargs) -> SandboxTradeSessionDeleteResponse:
        self._record("delete_session", kwargs)
        return SandboxTradeSessionDeleteResponse(
            id=str(kwargs["session_id"]),
            deleted=True,
        )

    async def list_ticks(self, **kwargs) -> SandboxTradeTickListResponse:
        self._record("list_ticks", kwargs)
        return SandboxTradeTickListResponse(items=[_tick_response()], total=1)

    async def list_orders(self, **kwargs) -> SandboxTradeOrderListResponse:
        self._record("list_orders", kwargs)
        return SandboxTradeOrderListResponse(items=[_order_response()], total=1)

    async def list_settlements(self, **kwargs) -> SandboxTradeSettlementListResponse:
        self._record("list_settlements", kwargs)
        return SandboxTradeSettlementListResponse(
            items=[_settlement_response()],
            total=1,
        )

    async def get_portfolio_state(self, **kwargs) -> SandboxTradePortfolioStateResponse:
        self._record("get_portfolio_state", kwargs)
        return SandboxTradePortfolioStateResponse(
            position=_position_response(),
            latest_snapshot=_snapshot_response(),
            pending_settlements=[_settlement_response()],
        )

    async def list_portfolio_snapshots(
        self,
        **kwargs,
    ) -> SandboxTradePortfolioSnapshotListResponse:
        self._record("list_portfolio_snapshots", kwargs)
        return SandboxTradePortfolioSnapshotListResponse(
            items=[_snapshot_response()],
            total=1,
        )


def _build_app(service: _FakeSandboxTradeAgentService) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.include_router(sandbox_trade_router, prefix="/api/v1")
    app.dependency_overrides[get_sandbox_trade_agent_session_service] = (
        lambda: service
    )
    app.dependency_overrides[get_current_active_user] = lambda: _user()
    app.dependency_overrides[get_current_organization_context] = (
        lambda: OrganizationContext(organization_id="org-1")
    )
    return app


@pytest.mark.asyncio
async def test_sandbox_trade_session_routes_use_user_and_organization_scope() -> None:
    service = _FakeSandboxTradeAgentService()
    app = _build_app(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        create_response = await client.post(
            "/api/v1/sandbox-trade-agent/sessions",
            json={"symbol": "fpt"},
        )
        list_response = await client.get(
            "/api/v1/sandbox-trade-agent/sessions",
            params={"page": 2, "page_size": 2},
        )
        get_response = await client.get(
            "/api/v1/sandbox-trade-agent/sessions/session-1"
        )
        update_response = await client.patch(
            "/api/v1/sandbox-trade-agent/sessions/session-1",
            json={"runtime_config": None},
        )
        pause_response = await client.post(
            "/api/v1/sandbox-trade-agent/sessions/session-1/pause"
        )
        resume_response = await client.post(
            "/api/v1/sandbox-trade-agent/sessions/session-1/resume"
        )
        stop_response = await client.post(
            "/api/v1/sandbox-trade-agent/sessions/session-1/stop"
        )
        delete_response = await client.delete(
            "/api/v1/sandbox-trade-agent/sessions/session-1"
        )

    assert create_response.status_code == 201
    assert create_response.json()["symbol"] == "FPT"
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 7
    assert list_response.json()["page"] == 2
    assert get_response.status_code == 200
    assert update_response.status_code == 200
    assert pause_response.json()["status"] == "paused"
    assert resume_response.json()["status"] == "active"
    assert stop_response.json()["status"] == "stopped"
    assert delete_response.json() == {"id": "session-1", "deleted": True}

    method_names = [method_name for method_name, _ in service.calls]
    assert method_names == [
        "create_session",
        "list_sessions",
        "get_session",
        "update_session",
        "pause_session",
        "resume_session",
        "stop_session",
        "delete_session",
    ]
    for _, kwargs in service.calls:
        assert kwargs["current_user"].id == "user-1"
        assert kwargs["organization_id"] == "org-1"


@pytest.mark.asyncio
async def test_sandbox_trade_history_routes_return_session_scoped_data() -> None:
    service = _FakeSandboxTradeAgentService()
    app = _build_app(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        ticks = await client.get(
            "/api/v1/sandbox-trade-agent/sessions/session-1/ticks"
        )
        orders = await client.get(
            "/api/v1/sandbox-trade-agent/sessions/session-1/orders"
        )
        settlements = await client.get(
            "/api/v1/sandbox-trade-agent/sessions/session-1/settlements"
        )
        portfolio = await client.get(
            "/api/v1/sandbox-trade-agent/sessions/session-1/portfolio"
        )
        snapshots = await client.get(
            "/api/v1/sandbox-trade-agent/sessions/session-1/portfolio/snapshots"
        )

    assert ticks.status_code == 200
    assert ticks.json()["items"][0]["status"] == "completed"
    assert orders.json()["items"][0]["status"] == "filled"
    assert settlements.json()["items"][0]["asset_type"] == "security"
    assert portfolio.json()["position"]["available_cash"] == 99_000_000
    assert snapshots.json()["items"][0]["equity"] == 100_000_000
    assert [method_name for method_name, _ in service.calls] == [
        "list_ticks",
        "list_orders",
        "list_settlements",
        "get_portfolio_state",
        "list_portfolio_snapshots",
    ]
    for _, kwargs in service.calls:
        assert kwargs["session_id"] == "session-1"
        assert kwargs["organization_id"] == "org-1"


@pytest.mark.asyncio
async def test_sandbox_trade_get_rejects_session_outside_owner_scope() -> None:
    service = _FakeSandboxTradeAgentService()
    service.raise_not_found = True
    app = _build_app(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/sandbox-trade-agent/sessions/other-session"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Sandbox trade session not found"
