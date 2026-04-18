from __future__ import annotations

from datetime import datetime, timezone
import importlib
import sys
import types

import pytest
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _load_test_dependencies(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    fake_service_module = types.ModuleType("app.common.service")

    def get_auth_service():  # pragma: no cover - import shim for app.api.deps
        raise AssertionError("Auth service should not be resolved in these tests")

    def get_backtest_service():  # pragma: no cover - dependency override target
        raise AssertionError(
            "Backtest service dependency should be overridden in these tests"
        )

    fake_service_module.get_auth_service = get_auth_service
    fake_service_module.get_backtest_service = get_backtest_service
    monkeypatch.setitem(sys.modules, "app.common.service", fake_service_module)

    deps_module = importlib.import_module("app.api.deps")
    backtests_router_module = importlib.import_module("app.api.v1.backtests.router")
    common_repo_module = importlib.import_module("app.common.repo")
    user_model_module = importlib.import_module("app.domain.models.user")
    backtest_schema_module = importlib.import_module("app.domain.schemas.backtest")
    templates_module = importlib.import_module("app.services.backtest.templates")

    return {
        "get_current_active_user": deps_module.get_current_active_user,
        "get_current_organization_context": deps_module.get_current_organization_context,
        "OrganizationContext": deps_module.OrganizationContext,
        "router": backtests_router_module.router,
        "get_backtest_service": backtests_router_module.get_backtest_service,
        "get_org_repo": common_repo_module.get_org_repo,
        "get_member_repo": common_repo_module.get_member_repo,
        "User": user_model_module.User,
        "UserRole": user_model_module.UserRole,
        "BacktestRunResponse": backtest_schema_module.BacktestRunResponse,
        "BacktestSummaryMetrics": backtest_schema_module.BacktestSummaryMetrics,
        "BacktestPerformanceMetrics": backtest_schema_module.BacktestPerformanceMetrics,
        "BacktestTradeLogEntry": backtest_schema_module.BacktestTradeLogEntry,
        "BacktestEquityCurvePoint": backtest_schema_module.BacktestEquityCurvePoint,
        "BacktestTemplateRegistry": templates_module.BacktestTemplateRegistry,
    }


def _build_user(test_deps: dict[str, object], *, user_id: str = "user-1"):
    user_model = test_deps["User"]
    user_role = test_deps["UserRole"]
    now = _utc(2026, 1, 1)
    return user_model(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        role=user_role.USER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


class _FakeBacktestService:
    def __init__(self, test_deps: dict[str, object]) -> None:
        self.template_registry = test_deps["BacktestTemplateRegistry"]()
        self.calls: list[object] = []
        self._schemas = test_deps

    async def run_backtest(self, request):
        self.calls.append(request)
        return self._schemas["BacktestRunResponse"](
            summary_metrics=self._schemas["BacktestSummaryMetrics"](
                symbol=request.symbol,
                template_id=request.template_id,
                timeframe="1D",
                date_from=request.date_from,
                date_to=request.date_to,
                initial_capital=request.initial_capital,
                ending_equity=120_000_000,
                total_trades=1,
            ),
            performance_metrics=self._schemas["BacktestPerformanceMetrics"](
                total_return_pct=20.0,
                annualized_return_pct=20.0,
                max_drawdown_pct=5.0,
                win_rate_pct=100.0,
                profit_factor=20_000_000.0,
                avg_win_pct=20.0,
                avg_loss_pct=0.0,
                expectancy=20.0,
            ),
            trade_log=[
                self._schemas["BacktestTradeLogEntry"](
                    entry_time="2024-01-02",
                    entry_price=100.0,
                    exit_time="2024-12-31",
                    exit_price=120.0,
                    shares=1_000_000,
                    invested_capital=100_000_000.0,
                    pnl=20_000_000.0,
                    pnl_pct=20.0,
                    exit_reason="end_of_window",
                )
            ],
            equity_curve=[
                self._schemas["BacktestEquityCurvePoint"](
                    time="2024-12-31",
                    cash=120_000_000.0,
                    market_value=0.0,
                    equity=120_000_000.0,
                    drawdown_pct=0.0,
                    position_size=0,
                )
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
    test_deps: dict[str, object],
    *,
    service: _FakeBacktestService,
    use_real_org_context: bool = False,
    org_repo: _FakeOrganizationRepo | None = None,
    member_repo: _FakeMemberRepo | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(test_deps["router"])
    app.dependency_overrides[test_deps["get_current_active_user"]] = lambda: _build_user(
        test_deps
    )
    app.dependency_overrides[test_deps["get_backtest_service"]] = lambda: service

    if not use_real_org_context:
        app.dependency_overrides[test_deps["get_current_organization_context"]] = (
            lambda: test_deps["OrganizationContext"](organization_id="org-1")
        )
    else:
        app.dependency_overrides[test_deps["get_org_repo"]] = (
            lambda: org_repo or _FakeOrganizationRepo()
        )
        app.dependency_overrides[test_deps["get_member_repo"]] = (
            lambda: member_repo or _FakeMemberRepo()
        )

    return app


@pytest.mark.asyncio
async def test_list_backtest_templates_returns_current_template_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_deps = _load_test_dependencies(monkeypatch)
    app = _build_test_app(test_deps, service=_FakeBacktestService(test_deps))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/backtests/templates")

    assert response.status_code == 200
    body = response.json()
    assert [item["template_id"] for item in body["items"]] == [
        "buy_and_hold",
        "sma_crossover",
        "ichimoku_cloud",
    ]
    assert body["items"][0]["parameters"] == []
    assert [parameter["name"] for parameter in body["items"][1]["parameters"]] == [
        "fast_window",
        "slow_window",
    ]
    assert [parameter["name"] for parameter in body["items"][2]["parameters"]] == [
        "tenkan_window",
        "kijun_window",
        "senkou_b_window",
        "displacement",
        "warmup_bars",
    ]


@pytest.mark.asyncio
async def test_run_backtest_maps_request_body_to_internal_request_and_returns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_deps = _load_test_dependencies(monkeypatch)
    service = _FakeBacktestService(test_deps)
    app = _build_test_app(test_deps, service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/backtests/run",
            json={
                "symbol": "fpt",
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
                "template_id": "sma_crossover",
                "template_params": {
                    "fast_window": 20,
                    "slow_window": 50,
                },
            },
        )

    assert response.status_code == 200
    assert len(service.calls) == 1
    request = service.calls[0]
    assert request.symbol == "FPT"
    assert request.template_id == "sma_crossover"
    assert request.initial_capital == 100_000_000
    assert request.timeframe == "1D"
    assert request.direction == "long_only"
    assert request.position_sizing == "all_in"
    assert request.execution_model == "next_open"

    body = response.json()
    assert body["result"]["summary_metrics"]["symbol"] == "FPT"
    assert body["assumptions"] == {
        "timeframe": "1D",
        "direction": "long_only",
        "position_sizing": "all_in",
        "execution_model": "next_open",
        "initial_capital": 100000000,
    }


@pytest.mark.asyncio
async def test_run_backtest_accepts_valid_ichimoku_public_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_deps = _load_test_dependencies(monkeypatch)
    service = _FakeBacktestService(test_deps)
    app = _build_test_app(test_deps, service=service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/backtests/run",
            json={
                "symbol": "fpt",
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
                "template_id": "ichimoku_cloud",
                "template_params": {
                    "tenkan_window": 9,
                    "kijun_window": 26,
                    "senkou_b_window": 52,
                    "displacement": 26,
                    "warmup_bars": 100,
                },
            },
        )

    assert response.status_code == 200
    assert len(service.calls) == 1
    request = service.calls[0]
    assert request.template_id == "ichimoku_cloud"
    assert request.template_params.warmup_bars == 100


@pytest.mark.asyncio
async def test_run_backtest_rejects_invalid_ichimoku_public_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_deps = _load_test_dependencies(monkeypatch)
    app = _build_test_app(test_deps, service=_FakeBacktestService(test_deps))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/backtests/run",
            json={
                "symbol": "fpt",
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
                "template_id": "ichimoku_cloud",
                "template_params": {
                    "tenkan_window": 26,
                    "kijun_window": 9,
                    "senkou_b_window": 52,
                    "displacement": 26,
                    "warmup_bars": 100,
                },
            },
        )

    assert response.status_code == 422
    assert "ichimoku windows must satisfy tenkan_window < kijun_window < senkou_b_window" in response.text


@pytest.mark.asyncio
async def test_run_backtest_rejects_fixed_engine_fields_in_public_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_deps = _load_test_dependencies(monkeypatch)
    app = _build_test_app(test_deps, service=_FakeBacktestService(test_deps))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/backtests/run",
            json={
                "symbol": "FPT",
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
                "template_id": "buy_and_hold",
                "timeframe": "1D",
            },
        )

    assert response.status_code == 422
    assert "timeframe" in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("GET", "/backtests/templates"), ("POST", "/backtests/run")])
async def test_backtest_endpoints_require_x_organization_id_header(
    method: str,
    path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_deps = _load_test_dependencies(monkeypatch)
    app = _build_test_app(
        test_deps,
        service=_FakeBacktestService(test_deps),
        use_real_org_context=True,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        if method == "GET":
            response = await client.get(path)
        else:
            response = await client.post(
                path,
                json={
                    "symbol": "FPT",
                    "date_from": "2024-01-01",
                    "date_to": "2024-12-31",
                    "template_id": "buy_and_hold",
                },
            )

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Organization-ID header is required"


@pytest.mark.asyncio
async def test_backtest_run_rejects_user_without_org_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_deps = _load_test_dependencies(monkeypatch)
    app = _build_test_app(
        test_deps,
        service=_FakeBacktestService(test_deps),
        use_real_org_context=True,
        member_repo=_FakeMemberRepo(memberships=set()),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/backtests/run",
            headers={"X-Organization-ID": "org-1"},
            json={
                "symbol": "FPT",
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
                "template_id": "buy_and_hold",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied"


@pytest.mark.asyncio
async def test_one_failing_backtest_endpoint_does_not_block_other_backtest_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_deps = _load_test_dependencies(monkeypatch)
    service = _FakeBacktestService(test_deps)
    app = _build_test_app(test_deps, service=service)

    async def _failing_run_backtest(_request):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="backtest run failed",
        )

    service.run_backtest = _failing_run_backtest  # type: ignore[method-assign]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        run_response = await client.post(
            "/backtests/run",
            json={
                "symbol": "FPT",
                "date_from": "2024-01-01",
                "date_to": "2024-12-31",
                "template_id": "buy_and_hold",
            },
        )
        template_response = await client.get("/backtests/templates")

    assert run_response.status_code == 502
    assert run_response.json()["detail"] == "backtest run failed"
    assert template_response.status_code == 200
    assert template_response.json()["items"][0]["template_id"] == "buy_and_hold"
