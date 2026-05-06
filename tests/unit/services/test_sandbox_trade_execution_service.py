from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.models.sandbox_trade_agent import (
    SandboxTradeAction,
    SandboxTradeDecision,
    SandboxTradeMarketSnapshot,
    SandboxTradeOrder,
    SandboxTradeOrderSide,
    SandboxTradeOrderStatus,
    SandboxTradePosition,
    SandboxTradeQuantityType,
    SandboxTradeSession,
    SandboxTradeSessionStatus,
    SandboxTradeSettlement,
    SandboxTradeSettlementAssetType,
    SandboxTradeSettlementStatus,
    SandboxTradeTick,
    SandboxTradeTickStatus,
)
from app.services.stocks.sandbox_trade_execution_service import (
    INSUFFICIENT_AVAILABLE_CASH,
    INSUFFICIENT_SELLABLE_QUANTITY,
    OUTSIDE_TRADING_WINDOW,
    SandboxTradeExecutionService,
)
from app.services.stocks.sandbox_trade_schedule_calculator import (
    parse_sandbox_trade_trading_windows,
)


def _utc(
    year: int = 2026,
    month: int = 5,
    day: int = 4,
    hour: int = 3,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _session() -> SandboxTradeSession:
    return SandboxTradeSession(
        _id="session-1",
        user_id="user-1",
        organization_id="org-1",
        symbol="FPT",
        status=SandboxTradeSessionStatus.ACTIVE,
        initial_capital=100_000_000,
        next_run_at=_utc(),
        created_at=_utc(),
        updated_at=_utc(),
    )


def _position(**updates: object) -> SandboxTradePosition:
    payload = {
        "_id": "position-1",
        "session_id": "session-1",
        "symbol": "FPT",
        "available_cash": 10_000_000,
        "pending_cash": 0,
        "total_quantity": 0,
        "sellable_quantity": 0,
        "pending_quantity": 0,
        "average_cost": 0,
        "realized_pnl": 0,
        "created_at": _utc(),
        "updated_at": _utc(),
    }
    payload.update(updates)
    return SandboxTradePosition(**payload)


def _tick(
    *,
    action: SandboxTradeAction,
    quantity_type: SandboxTradeQuantityType | None = SandboxTradeQuantityType.SHARES,
    quantity_value: float | None = 10,
    price: float = 100_000,
) -> SandboxTradeTick:
    return SandboxTradeTick(
        _id="tick-1",
        session_id="session-1",
        tick_at=_utc(),
        status=SandboxTradeTickStatus.RUNNING,
        lock_token="lock-1",
        market_snapshot=SandboxTradeMarketSnapshot(
            symbol="FPT",
            source="VCI",
            latest_price=price,
            observed_at=_utc(),
        ),
        decision=SandboxTradeDecision(
            action=action,
            quantity_type=quantity_type,
            quantity_value=quantity_value,
            reason="test",
        ),
        created_at=_utc(),
        updated_at=_utc(),
    )


class _TickRepo:
    def __init__(self, *, owns_lock: bool = True) -> None:
        self.owns_lock = owns_lock
        self.completed: list[dict[str, object]] = []
        self.rejected: list[dict[str, object]] = []

    async def is_running_with_lock(self, **kwargs) -> bool:
        return self.owns_lock

    async def mark_completed(self, **kwargs) -> SandboxTradeTick:
        self.completed.append(kwargs)
        return _tick(action=SandboxTradeAction.HOLD).model_copy(
            update={
                "status": SandboxTradeTickStatus.COMPLETED,
                "completed_at": kwargs["completed_at"],
                "order_id": kwargs.get("order_id"),
            }
        )

    async def mark_rejected_execution(self, **kwargs) -> SandboxTradeTick:
        self.rejected.append(kwargs)
        return _tick(action=SandboxTradeAction.BUY).model_copy(
            update={
                "status": SandboxTradeTickStatus.REJECTED,
                "completed_at": kwargs["completed_at"],
                "rejection_reason": kwargs["rejection_reason"],
                "order_id": kwargs.get("order_id"),
            }
        )

    async def mark_failed(self, **kwargs) -> SandboxTradeTick:
        return _tick(action=SandboxTradeAction.HOLD).model_copy(
            update={
                "status": SandboxTradeTickStatus.FAILED,
                "completed_at": kwargs["completed_at"],
                "error": kwargs["error"],
            }
        )


class _OrderRepo:
    def __init__(self) -> None:
        self.filled: list[dict[str, object]] = []
        self.rejected: list[dict[str, object]] = []

    async def create_filled(self, **kwargs) -> SandboxTradeOrder:
        self.filled.append(kwargs)
        return SandboxTradeOrder(
            _id=f"order-filled-{len(self.filled)}",
            status=SandboxTradeOrderStatus.FILLED,
            created_at=_utc(),
            updated_at=_utc(),
            **kwargs,
        )

    async def create_rejected(self, **kwargs) -> SandboxTradeOrder:
        self.rejected.append(kwargs)
        return SandboxTradeOrder(
            _id=f"order-rejected-{len(self.rejected)}",
            status=SandboxTradeOrderStatus.REJECTED,
            created_at=_utc(),
            updated_at=_utc(),
            **kwargs,
        )


class _PositionRepo:
    def __init__(self, position: SandboxTradePosition) -> None:
        self.position = position
        self.buy_calls: list[dict[str, object]] = []
        self.sell_calls: list[dict[str, object]] = []
        self.cash_settlements: list[dict[str, object]] = []
        self.security_settlements: list[dict[str, object]] = []

    async def find_by_session(self, **kwargs) -> SandboxTradePosition:
        return self.position

    async def apply_buy_fill(self, **kwargs) -> SandboxTradePosition:
        self.buy_calls.append(kwargs)
        self.position = self.position.model_copy(
            update={
                "available_cash": self.position.available_cash
                - kwargs["gross_amount"],
                "total_quantity": self.position.total_quantity
                + kwargs["quantity"],
                "pending_quantity": self.position.pending_quantity
                + kwargs["quantity"],
                "average_cost": kwargs["average_cost"],
            }
        )
        return self.position

    async def apply_sell_fill(self, **kwargs) -> SandboxTradePosition:
        self.sell_calls.append(kwargs)
        self.position = self.position.model_copy(
            update={
                "total_quantity": self.position.total_quantity - kwargs["quantity"],
                "sellable_quantity": self.position.sellable_quantity
                - kwargs["quantity"],
                "pending_cash": self.position.pending_cash + kwargs["gross_amount"],
                "realized_pnl": self.position.realized_pnl
                + kwargs["realized_pnl_delta"],
                "average_cost": kwargs["average_cost"],
            }
        )
        return self.position

    async def apply_cash_settlement(self, **kwargs) -> SandboxTradePosition:
        self.cash_settlements.append(kwargs)
        self.position = self.position.model_copy(
            update={
                "available_cash": self.position.available_cash + kwargs["amount"],
                "pending_cash": self.position.pending_cash - kwargs["amount"],
            }
        )
        return self.position

    async def apply_security_settlement(self, **kwargs) -> SandboxTradePosition:
        self.security_settlements.append(kwargs)
        self.position = self.position.model_copy(
            update={
                "sellable_quantity": self.position.sellable_quantity
                + kwargs["quantity"],
                "pending_quantity": self.position.pending_quantity
                - kwargs["quantity"],
            }
        )
        return self.position


class _SettlementRepo:
    def __init__(self, due: list[SandboxTradeSettlement] | None = None) -> None:
        self.created: list[dict[str, object]] = []
        self.settled: list[dict[str, object]] = []
        self.due = due or []

    async def create_pending(self, **kwargs) -> SandboxTradeSettlement:
        self.created.append(kwargs)
        return SandboxTradeSettlement(
            _id=f"settlement-{len(self.created)}",
            status=SandboxTradeSettlementStatus.PENDING,
            created_at=_utc(),
            updated_at=_utc(),
            **kwargs,
        )

    async def list_due_pending_by_session(self, **kwargs):
        return self.due

    async def mark_settled(self, **kwargs):
        self.settled.append(kwargs)


class _SnapshotService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def persist_for_tick(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _service(
    *,
    position: SandboxTradePosition,
    tick_repo: _TickRepo | None = None,
    settlement_repo: _SettlementRepo | None = None,
) -> tuple[
    SandboxTradeExecutionService,
    _TickRepo,
    _OrderRepo,
    _PositionRepo,
    _SettlementRepo,
    _SnapshotService,
]:
    tick_repo = tick_repo or _TickRepo()
    order_repo = _OrderRepo()
    position_repo = _PositionRepo(position)
    settlement_repo = settlement_repo or _SettlementRepo()
    snapshot_service = _SnapshotService()
    service = SandboxTradeExecutionService(
        tick_repo=tick_repo,
        order_repo=order_repo,
        position_repo=position_repo,
        settlement_repo=settlement_repo,
        portfolio_snapshot_service=snapshot_service,
        windows=parse_sandbox_trade_trading_windows(),
    )
    return (
        service,
        tick_repo,
        order_repo,
        position_repo,
        settlement_repo,
        snapshot_service,
    )


@pytest.mark.asyncio
async def test_buy_with_sufficient_cash_reduces_available_cash_and_settles_security():
    service, tick_repo, order_repo, position_repo, settlement_repo, snapshot = _service(
        position=_position(available_cash=2_000_000)
    )

    result = await service.execute_tick_decision(
        session=_session(),
        tick=_tick(action=SandboxTradeAction.BUY, quantity_value=10),
        position=position_repo.position,
        now=_utc(2026, 5, 4, 3),
    )

    assert result.tick.status == SandboxTradeTickStatus.COMPLETED
    assert result.position.available_cash == 1_000_000
    assert result.position.pending_quantity == 10
    assert order_repo.filled[0]["side"] == SandboxTradeOrderSide.BUY
    assert settlement_repo.created[0]["asset_type"] == (
        SandboxTradeSettlementAssetType.SECURITY
    )
    assert settlement_repo.created[0]["quantity"] == 10
    assert tick_repo.completed[0]["order_id"] == "order-filled-1"
    assert len(snapshot.calls) == 1


@pytest.mark.asyncio
async def test_buy_with_insufficient_cash_is_rejected_without_fill() -> None:
    service, _, order_repo, position_repo, settlement_repo, _ = _service(
        position=_position(available_cash=500_000)
    )

    result = await service.execute_tick_decision(
        session=_session(),
        tick=_tick(action=SandboxTradeAction.BUY, quantity_value=10),
        position=position_repo.position,
        now=_utc(2026, 5, 4, 3),
    )

    assert result.tick.status == SandboxTradeTickStatus.REJECTED
    assert result.tick.rejection_reason == INSUFFICIENT_AVAILABLE_CASH
    assert order_repo.filled == []
    assert order_repo.rejected[0]["rejection_reason"] == INSUFFICIENT_AVAILABLE_CASH
    assert settlement_repo.created == []


@pytest.mark.asyncio
async def test_sell_with_sufficient_sellable_quantity_creates_pending_cash() -> None:
    service, _, order_repo, position_repo, settlement_repo, _ = _service(
        position=_position(
            total_quantity=20,
            sellable_quantity=20,
            average_cost=80_000,
        )
    )

    result = await service.execute_tick_decision(
        session=_session(),
        tick=_tick(action=SandboxTradeAction.SELL, quantity_value=5),
        position=position_repo.position,
        now=_utc(2026, 5, 4, 3),
    )

    assert result.tick.status == SandboxTradeTickStatus.COMPLETED
    assert result.position.sellable_quantity == 15
    assert result.position.pending_cash == 500_000
    assert result.position.realized_pnl == 100_000
    assert order_repo.filled[0]["side"] == SandboxTradeOrderSide.SELL
    assert settlement_repo.created[0]["asset_type"] == (
        SandboxTradeSettlementAssetType.CASH
    )
    assert settlement_repo.created[0]["amount"] == 500_000


@pytest.mark.asyncio
async def test_unsettled_security_sell_is_rejected() -> None:
    service, _, order_repo, position_repo, settlement_repo, _ = _service(
        position=_position(
            total_quantity=10,
            sellable_quantity=0,
            pending_quantity=10,
            average_cost=100_000,
        )
    )

    result = await service.execute_tick_decision(
        session=_session(),
        tick=_tick(action=SandboxTradeAction.SELL, quantity_value=1),
        position=position_repo.position,
        now=_utc(2026, 5, 4, 3),
    )

    assert result.tick.status == SandboxTradeTickStatus.REJECTED
    assert result.tick.rejection_reason == INSUFFICIENT_SELLABLE_QUANTITY
    assert order_repo.filled == []
    assert settlement_repo.created == []


@pytest.mark.asyncio
async def test_trade_outside_window_is_rejected_without_fill() -> None:
    service, _, order_repo, position_repo, settlement_repo, _ = _service(
        position=_position(available_cash=2_000_000)
    )

    result = await service.execute_tick_decision(
        session=_session(),
        tick=_tick(action=SandboxTradeAction.BUY, quantity_value=1),
        position=position_repo.position,
        now=_utc(2026, 5, 4, 8),
    )

    assert result.tick.status == SandboxTradeTickStatus.REJECTED
    assert result.tick.rejection_reason == OUTSIDE_TRADING_WINDOW
    assert order_repo.filled == []
    assert order_repo.rejected[0]["rejection_reason"] == OUTSIDE_TRADING_WINDOW
    assert settlement_repo.created == []


@pytest.mark.asyncio
async def test_due_cash_and_security_settlements_update_position_before_agent() -> None:
    due = [
        SandboxTradeSettlement(
            _id="settlement-cash",
            session_id="session-1",
            order_id="order-1",
            symbol="FPT",
            asset_type=SandboxTradeSettlementAssetType.CASH,
            amount=1_000_000,
            trade_date="2026-04-30",
            settle_at=_utc(2026, 5, 4, 0),
            created_at=_utc(),
            updated_at=_utc(),
        ),
        SandboxTradeSettlement(
            _id="settlement-security",
            session_id="session-1",
            order_id="order-2",
            symbol="FPT",
            asset_type=SandboxTradeSettlementAssetType.SECURITY,
            quantity=10,
            trade_date="2026-04-30",
            settle_at=_utc(2026, 5, 4, 0),
            created_at=_utc(),
            updated_at=_utc(),
        ),
    ]
    settlement_repo = _SettlementRepo(due=due)
    service, _, _, position_repo, _, _ = _service(
        position=_position(
            available_cash=2_000_000,
            pending_cash=1_000_000,
            total_quantity=10,
            sellable_quantity=0,
            pending_quantity=10,
        ),
        settlement_repo=settlement_repo,
    )

    position = await service.apply_due_settlements(session=_session(), now=_utc())

    assert position.available_cash == 3_000_000
    assert position.pending_cash == 0
    assert position.sellable_quantity == 10
    assert position.pending_quantity == 0
    assert len(settlement_repo.settled) == 2
    assert position_repo.cash_settlements[0]["amount"] == 1_000_000
    assert position_repo.security_settlements[0]["quantity"] == 10


@pytest.mark.asyncio
async def test_lost_tick_lock_prevents_execution_side_effects() -> None:
    service, _, order_repo, position_repo, settlement_repo, _ = _service(
        position=_position(available_cash=2_000_000),
        tick_repo=_TickRepo(owns_lock=False),
    )

    result = await service.execute_tick_decision(
        session=_session(),
        tick=_tick(action=SandboxTradeAction.BUY, quantity_value=10),
        position=position_repo.position,
        now=_utc(2026, 5, 4, 3),
    )

    assert result.tick.status == SandboxTradeTickStatus.RUNNING
    assert order_repo.filled == []
    assert order_repo.rejected == []
    assert settlement_repo.created == []
