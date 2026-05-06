"""Sandbox order execution and T+2 settlement accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.models.sandbox_trade_agent import (
    SandboxTradeAction,
    SandboxTradeOrder,
    SandboxTradeOrderSide,
    SandboxTradePosition,
    SandboxTradeQuantityType,
    SandboxTradeSession,
    SandboxTradeSettlementAssetType,
    SandboxTradeTick,
)
from app.repo.sandbox_trade_agent_repo import (
    SandboxTradeOrderRepository,
    SandboxTradePositionRepository,
    SandboxTradeSettlementRepository,
    SandboxTradeTickRepository,
)
from app.services.stocks.sandbox_trade_portfolio_snapshot_service import (
    SandboxTradePortfolioSnapshotService,
)
from app.services.stocks.sandbox_trade_schedule_calculator import (
    SANDBOX_TRADE_TIMEZONE,
    SandboxTradeTradingWindow,
    is_sandbox_trade_trading_time,
)
from app.services.stocks.sandbox_trade_settlement_calculator import (
    calculate_sandbox_trade_settle_at,
)

INSUFFICIENT_AVAILABLE_CASH = "INSUFFICIENT_AVAILABLE_CASH"
INSUFFICIENT_SELLABLE_QUANTITY = "INSUFFICIENT_SELLABLE_QUANTITY"
OUTSIDE_TRADING_WINDOW = "OUTSIDE_TRADING_WINDOW"
INVALID_EXECUTION_INPUT = "INVALID_EXECUTION_INPUT"
FLOAT_EPSILON = 1e-9


@dataclass(frozen=True)
class SandboxTradeExecutionResult:
    """Result of applying one sandbox decision to portfolio accounting."""

    tick: SandboxTradeTick
    position: SandboxTradePosition | None
    order: SandboxTradeOrder | None = None


class SandboxTradeExecutionService:
    """Validate decisions, create sandbox fills, settle ledger entries, snapshot."""

    def __init__(
        self,
        *,
        tick_repo: SandboxTradeTickRepository,
        order_repo: SandboxTradeOrderRepository,
        position_repo: SandboxTradePositionRepository,
        settlement_repo: SandboxTradeSettlementRepository,
        portfolio_snapshot_service: SandboxTradePortfolioSnapshotService,
        windows: tuple[SandboxTradeTradingWindow, ...],
    ) -> None:
        self.tick_repo = tick_repo
        self.order_repo = order_repo
        self.position_repo = position_repo
        self.settlement_repo = settlement_repo
        self.portfolio_snapshot_service = portfolio_snapshot_service
        self.windows = windows

    async def apply_due_settlements(
        self,
        *,
        session: SandboxTradeSession,
        now: datetime | None = None,
    ) -> SandboxTradePosition | None:
        """Apply all due pending settlements before the next agent input is built."""
        if session.id is None:
            return None

        process_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        due_settlements = await self.settlement_repo.list_due_pending_by_session(
            session_id=session.id,
            due_at=process_now,
        )
        position: SandboxTradePosition | None = None

        for settlement in due_settlements:
            if settlement.id is None:
                continue
            if settlement.asset_type == SandboxTradeSettlementAssetType.CASH:
                if settlement.amount is None or settlement.amount <= 0:
                    continue
                position = await self.position_repo.apply_cash_settlement(
                    session_id=session.id,
                    amount=settlement.amount,
                    now=process_now,
                )
            elif settlement.asset_type == SandboxTradeSettlementAssetType.SECURITY:
                if settlement.quantity is None or settlement.quantity <= 0:
                    continue
                position = await self.position_repo.apply_security_settlement(
                    session_id=session.id,
                    quantity=settlement.quantity,
                    now=process_now,
                )
            else:
                continue

            if position is not None:
                await self.settlement_repo.mark_settled(
                    settlement_id=settlement.id,
                    settled_at=process_now,
                )

        return position or await self.position_repo.find_by_session(
            session_id=session.id
        )

    async def execute_tick_decision(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        position: SandboxTradePosition,
        now: datetime | None = None,
    ) -> SandboxTradeExecutionResult:
        """Execute a valid structured decision against sandbox accounting."""
        process_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if tick.decision is None or tick.market_snapshot is None:
            failed_tick = await self._mark_failed_and_snapshot(
                session=session,
                tick=tick,
                position=position,
                error=INVALID_EXECUTION_INPUT,
                completed_at=process_now,
            )
            return SandboxTradeExecutionResult(tick=failed_tick, position=position)

        if not await self._still_owns_tick(tick):
            return SandboxTradeExecutionResult(tick=tick, position=position)

        if tick.decision.action == SandboxTradeAction.HOLD:
            completed_tick = await self._mark_completed_and_snapshot(
                session=session,
                tick=tick,
                position=position,
                order_id=None,
                completed_at=process_now,
            )
            return SandboxTradeExecutionResult(
                tick=completed_tick,
                position=position,
                order=None,
            )

        side = self._decision_side(tick)
        price = tick.market_snapshot.latest_price
        quantity = self._decision_quantity(
            tick=tick,
            position=position,
            price=price,
        )
        gross_amount = quantity * price

        if not is_sandbox_trade_trading_time(process_now, windows=self.windows):
            return await self._reject_order_and_snapshot(
                session=session,
                tick=tick,
                position=position,
                side=side,
                quantity=quantity,
                price=price,
                gross_amount=gross_amount,
                rejection_reason=OUTSIDE_TRADING_WINDOW,
                completed_at=process_now,
            )

        if side == SandboxTradeOrderSide.BUY:
            if gross_amount > position.available_cash + FLOAT_EPSILON:
                return await self._reject_order_and_snapshot(
                    session=session,
                    tick=tick,
                    position=position,
                    side=side,
                    quantity=quantity,
                    price=price,
                    gross_amount=gross_amount,
                    rejection_reason=INSUFFICIENT_AVAILABLE_CASH,
                    completed_at=process_now,
                )
            return await self._fill_buy(
                session=session,
                tick=tick,
                position=position,
                quantity=quantity,
                price=price,
                gross_amount=gross_amount,
                filled_at=process_now,
            )

        if quantity > position.sellable_quantity + FLOAT_EPSILON:
            return await self._reject_order_and_snapshot(
                session=session,
                tick=tick,
                position=position,
                side=side,
                quantity=quantity,
                price=price,
                gross_amount=gross_amount,
                rejection_reason=INSUFFICIENT_SELLABLE_QUANTITY,
                completed_at=process_now,
            )
        return await self._fill_sell(
            session=session,
            tick=tick,
            position=position,
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            filled_at=process_now,
        )

    async def record_failed_tick(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        position: SandboxTradePosition | None = None,
        error: str,
        now: datetime | None = None,
    ) -> SandboxTradeTick:
        """Mark and snapshot a failed tick from worker orchestration."""
        process_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        current_position = position
        if current_position is None and session.id is not None:
            current_position = await self.position_repo.find_by_session(
                session_id=session.id
            )
        return await self._mark_failed_and_snapshot(
            session=session,
            tick=tick,
            position=current_position,
            error=error,
            completed_at=process_now,
        )

    async def _fill_buy(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        position: SandboxTradePosition,
        quantity: float,
        price: float,
        gross_amount: float,
        filled_at: datetime,
    ) -> SandboxTradeExecutionResult:
        trade_date = self._trade_date(filled_at)
        order = await self.order_repo.create_filled(
            session_id=session.id,
            tick_id=tick.id,
            symbol=session.symbol,
            side=SandboxTradeOrderSide.BUY,
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            filled_at=filled_at,
            trade_date=trade_date,
        )
        updated_position = await self.position_repo.apply_buy_fill(
            session_id=session.id,
            quantity=quantity,
            gross_amount=gross_amount,
            average_cost=self._buy_average_cost(
                position=position,
                quantity=quantity,
                gross_amount=gross_amount,
            ),
            now=filled_at,
        )
        await self.settlement_repo.create_pending(
            session_id=session.id,
            order_id=order.id,
            symbol=session.symbol,
            asset_type=SandboxTradeSettlementAssetType.SECURITY,
            quantity=quantity,
            trade_date=trade_date,
            settle_at=calculate_sandbox_trade_settle_at(trade_at=filled_at),
        )
        completed_tick = await self._mark_completed_and_snapshot(
            session=session,
            tick=tick,
            position=updated_position or position,
            order_id=order.id,
            completed_at=filled_at,
        )
        return SandboxTradeExecutionResult(
            tick=completed_tick,
            position=updated_position,
            order=order,
        )

    async def _fill_sell(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        position: SandboxTradePosition,
        quantity: float,
        price: float,
        gross_amount: float,
        filled_at: datetime,
    ) -> SandboxTradeExecutionResult:
        trade_date = self._trade_date(filled_at)
        order = await self.order_repo.create_filled(
            session_id=session.id,
            tick_id=tick.id,
            symbol=session.symbol,
            side=SandboxTradeOrderSide.SELL,
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            filled_at=filled_at,
            trade_date=trade_date,
        )
        remaining_quantity = max(position.total_quantity - quantity, 0)
        average_cost = position.average_cost if remaining_quantity > 0 else 0
        updated_position = await self.position_repo.apply_sell_fill(
            session_id=session.id,
            quantity=quantity,
            gross_amount=gross_amount,
            realized_pnl_delta=(price - position.average_cost) * quantity,
            average_cost=average_cost,
            now=filled_at,
        )
        await self.settlement_repo.create_pending(
            session_id=session.id,
            order_id=order.id,
            symbol=session.symbol,
            asset_type=SandboxTradeSettlementAssetType.CASH,
            amount=gross_amount,
            trade_date=trade_date,
            settle_at=calculate_sandbox_trade_settle_at(trade_at=filled_at),
        )
        completed_tick = await self._mark_completed_and_snapshot(
            session=session,
            tick=tick,
            position=updated_position or position,
            order_id=order.id,
            completed_at=filled_at,
        )
        return SandboxTradeExecutionResult(
            tick=completed_tick,
            position=updated_position,
            order=order,
        )

    async def _reject_order_and_snapshot(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        position: SandboxTradePosition,
        side: SandboxTradeOrderSide,
        quantity: float,
        price: float,
        gross_amount: float,
        rejection_reason: str,
        completed_at: datetime,
    ) -> SandboxTradeExecutionResult:
        order = await self.order_repo.create_rejected(
            session_id=session.id,
            tick_id=tick.id,
            symbol=session.symbol,
            side=side,
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            rejection_reason=rejection_reason,
            trade_date=self._trade_date(completed_at),
        )
        rejected_tick = await self.tick_repo.mark_rejected_execution(
            tick_id=tick.id,
            lock_token=tick.lock_token,
            completed_at=completed_at,
            rejection_reason=rejection_reason,
            order_id=order.id,
        )
        if rejected_tick is None:
            return SandboxTradeExecutionResult(
                tick=tick,
                position=position,
                order=order,
            )

        terminal_tick = rejected_tick.model_copy(
            update={
                "order_id": order.id,
                "rejection_reason": rejection_reason,
                "completed_at": completed_at,
            }
        )
        await self.portfolio_snapshot_service.persist_for_tick(
            session=session,
            tick=terminal_tick,
            position=position,
            now=completed_at,
        )
        return SandboxTradeExecutionResult(
            tick=terminal_tick,
            position=position,
            order=order,
        )

    async def _mark_completed_and_snapshot(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        position: SandboxTradePosition,
        order_id: str | None,
        completed_at: datetime,
    ) -> SandboxTradeTick:
        if tick.id is None or tick.lock_token is None:
            terminal_tick = tick.model_copy(
                update={"order_id": order_id, "completed_at": completed_at}
            )
        else:
            updated = await self.tick_repo.mark_completed(
                tick_id=tick.id,
                lock_token=tick.lock_token,
                completed_at=completed_at,
                order_id=order_id,
            )
            if updated is None:
                return tick
            terminal_tick = updated
        await self.portfolio_snapshot_service.persist_for_tick(
            session=session,
            tick=terminal_tick,
            position=position,
            now=completed_at,
        )
        return terminal_tick

    async def _mark_failed_and_snapshot(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        position: SandboxTradePosition | None,
        error: str,
        completed_at: datetime,
    ) -> SandboxTradeTick:
        if tick.id is None or tick.lock_token is None:
            terminal_tick = tick.model_copy(
                update={"error": error, "completed_at": completed_at}
            )
        else:
            updated = await self.tick_repo.mark_failed(
                tick_id=tick.id,
                lock_token=tick.lock_token,
                completed_at=completed_at,
                error=error,
            )
            if updated is None:
                return tick
            terminal_tick = updated
        await self.portfolio_snapshot_service.persist_for_tick(
            session=session,
            tick=terminal_tick,
            position=position,
            now=completed_at,
        )
        return terminal_tick

    @staticmethod
    def _decision_side(tick: SandboxTradeTick) -> SandboxTradeOrderSide:
        if tick.decision is None:
            raise ValueError("tick decision is required")
        if tick.decision.action == SandboxTradeAction.BUY:
            return SandboxTradeOrderSide.BUY
        return SandboxTradeOrderSide.SELL

    @staticmethod
    def _decision_quantity(
        *,
        tick: SandboxTradeTick,
        position: SandboxTradePosition,
        price: float,
    ) -> float:
        if tick.decision is None:
            raise ValueError("tick decision is required")
        if tick.decision.quantity_type == SandboxTradeQuantityType.SHARES:
            return float(tick.decision.quantity_value or 0)
        if tick.decision.quantity_type == SandboxTradeQuantityType.PERCENT_CASH:
            budget = position.available_cash * float(tick.decision.quantity_value or 0)
            return budget / 100 / price if price > 0 else 0
        if tick.decision.quantity_type == SandboxTradeQuantityType.PERCENT_POSITION:
            percent = float(tick.decision.quantity_value or 0)
            return position.sellable_quantity * percent / 100
        return 0

    @staticmethod
    def _buy_average_cost(
        *,
        position: SandboxTradePosition,
        quantity: float,
        gross_amount: float,
    ) -> float:
        new_quantity = position.total_quantity + quantity
        if new_quantity <= 0:
            return 0
        previous_cost = position.average_cost * position.total_quantity
        return (previous_cost + gross_amount) / new_quantity

    @staticmethod
    def _trade_date(value: datetime) -> str:
        return value.astimezone(SANDBOX_TRADE_TIMEZONE).date().isoformat()

    async def _still_owns_tick(self, tick: SandboxTradeTick) -> bool:
        if tick.id is None or tick.lock_token is None:
            return True
        return await self.tick_repo.is_running_with_lock(
            tick_id=tick.id,
            lock_token=tick.lock_token,
        )
