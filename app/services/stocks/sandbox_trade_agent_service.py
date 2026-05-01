"""Service layer for sandbox trade-agent session management."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.common.exceptions import (
    InvalidSandboxTradeSessionStateError,
    SandboxTradeSessionNotFoundError,
    StockSymbolNotFoundError,
)
from app.domain.models.sandbox_trade_agent import (
    SandboxTradeAgentRuntimeConfig,
    SandboxTradeOrder,
    SandboxTradePortfolioSnapshot,
    SandboxTradePosition,
    SandboxTradeSession,
    SandboxTradeSessionStatus,
    SandboxTradeSettlement,
    SandboxTradeTick,
)
from app.domain.models.user import User
from app.domain.schemas.sandbox_trade_agent import (
    SandboxTradeAgentRuntimeConfigResponse,
    SandboxTradeDecisionResponse,
    SandboxTradeMarketSnapshotResponse,
    SandboxTradeOrderListResponse,
    SandboxTradeOrderResponse,
    SandboxTradePortfolioSnapshotListResponse,
    SandboxTradePortfolioSnapshotResponse,
    SandboxTradePortfolioStateResponse,
    SandboxTradePositionResponse,
    SandboxTradeSessionCreateRequest,
    SandboxTradeSessionDeleteResponse,
    SandboxTradeSessionLifecycleResponse,
    SandboxTradeSessionListResponse,
    SandboxTradeSessionResponse,
    SandboxTradeSessionSummary,
    SandboxTradeSessionUpdateRequest,
    SandboxTradeSettlementListResponse,
    SandboxTradeSettlementResponse,
    SandboxTradeTickListResponse,
    SandboxTradeTickResponse,
)
from app.repo.sandbox_trade_agent_repo import (
    SandboxTradeOrderRepository,
    SandboxTradePortfolioSnapshotRepository,
    SandboxTradePositionRepository,
    SandboxTradeSessionRepository,
    SandboxTradeSettlementRepository,
    SandboxTradeTickRepository,
)
from app.repo.stock_symbol_repo import StockSymbolRepository


class SandboxTradeAgentSessionService:
    """Coordinate sandbox trade-agent session CRUD and history reads."""

    def __init__(
        self,
        *,
        session_repo: SandboxTradeSessionRepository,
        tick_repo: SandboxTradeTickRepository,
        order_repo: SandboxTradeOrderRepository,
        position_repo: SandboxTradePositionRepository,
        settlement_repo: SandboxTradeSettlementRepository,
        snapshot_repo: SandboxTradePortfolioSnapshotRepository,
        stock_repo: StockSymbolRepository,
        next_run_at_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_repo = session_repo
        self.tick_repo = tick_repo
        self.order_repo = order_repo
        self.position_repo = position_repo
        self.settlement_repo = settlement_repo
        self.snapshot_repo = snapshot_repo
        self.stock_repo = stock_repo
        self.next_run_at_factory = next_run_at_factory or _default_next_run_at

    async def create_session(
        self,
        *,
        current_user: User,
        organization_id: str,
        request: SandboxTradeSessionCreateRequest,
    ) -> SandboxTradeSessionResponse:
        """Validate and create one sandbox trade-agent session."""
        symbol = request.symbol.strip().upper()
        await self._ensure_symbol_exists(symbol)
        runtime_config = self._to_runtime_config_model(request.runtime_config)
        next_run_at = self.next_run_at_factory()

        session = await self.session_repo.create(
            user_id=current_user.id,
            organization_id=organization_id,
            symbol=symbol,
            initial_capital=request.initial_capital,
            runtime_config=runtime_config,
            next_run_at=next_run_at,
        )
        await self.position_repo.create_initial(
            session_id=session.id,
            symbol=session.symbol,
            initial_capital=session.initial_capital,
        )
        return self._to_session_response(session)

    async def list_sessions(
        self,
        *,
        current_user: User,
        organization_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> SandboxTradeSessionListResponse:
        """List one caller's non-deleted sandbox sessions in an organization."""
        sessions, total = await self.session_repo.list_by_user_and_organization(
            user_id=current_user.id,
            organization_id=organization_id,
            page=page,
            page_size=page_size,
        )
        return SandboxTradeSessionListResponse(
            items=[self._to_session_summary(session) for session in sessions],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_session(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
    ) -> SandboxTradeSessionResponse:
        """Read one caller-owned sandbox trade session."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        return self._to_session_response(session)

    async def update_session(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
        request: SandboxTradeSessionUpdateRequest,
    ) -> SandboxTradeSessionResponse:
        """Update mutable fields on one caller-owned sandbox trade session."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        self._ensure_mutable(session)
        if request.runtime_config is None:
            return self._to_session_response(session)

        updated = await self.session_repo.update_owned_session(
            session_id=session.id,
            user_id=current_user.id,
            organization_id=organization_id,
            runtime_config=self._to_runtime_config_model(request.runtime_config),
        )
        if updated is None:
            raise SandboxTradeSessionNotFoundError()
        return self._to_session_response(updated)

    async def pause_session(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
    ) -> SandboxTradeSessionLifecycleResponse:
        """Pause one active caller-owned sandbox trade session."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        if session.status != SandboxTradeSessionStatus.ACTIVE:
            raise InvalidSandboxTradeSessionStateError(
                "Only active sandbox trade sessions can be paused"
            )
        updated = await self._set_session_status(
            session=session,
            current_user=current_user,
            organization_id=organization_id,
            status=SandboxTradeSessionStatus.PAUSED,
        )
        return self._to_lifecycle_response(updated)

    async def resume_session(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
    ) -> SandboxTradeSessionLifecycleResponse:
        """Resume one paused caller-owned sandbox trade session."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        if session.status != SandboxTradeSessionStatus.PAUSED:
            raise InvalidSandboxTradeSessionStateError(
                "Only paused sandbox trade sessions can be resumed"
            )
        updated = await self._set_session_status(
            session=session,
            current_user=current_user,
            organization_id=organization_id,
            status=SandboxTradeSessionStatus.ACTIVE,
            next_run_at=self.next_run_at_factory(),
        )
        return self._to_lifecycle_response(updated)

    async def stop_session(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
    ) -> SandboxTradeSessionLifecycleResponse:
        """Stop one caller-owned sandbox trade session permanently."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        if session.status == SandboxTradeSessionStatus.STOPPED:
            return self._to_lifecycle_response(session)
        if session.status not in {
            SandboxTradeSessionStatus.ACTIVE,
            SandboxTradeSessionStatus.PAUSED,
        }:
            raise InvalidSandboxTradeSessionStateError()
        updated = await self._set_session_status(
            session=session,
            current_user=current_user,
            organization_id=organization_id,
            status=SandboxTradeSessionStatus.STOPPED,
        )
        return self._to_lifecycle_response(updated)

    async def delete_session(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
    ) -> SandboxTradeSessionDeleteResponse:
        """Soft-delete one caller-owned sandbox trade session."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        deleted = await self.session_repo.soft_delete_owned_session(
            session_id=session.id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        if deleted is None:
            raise SandboxTradeSessionNotFoundError()
        return SandboxTradeSessionDeleteResponse(id=session.id, deleted=True)

    async def list_ticks(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> SandboxTradeTickListResponse:
        """List tick history for one caller-owned session."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        ticks, total = await self.tick_repo.list_by_session(
            session_id=session.id,
            page=page,
            page_size=page_size,
        )
        return SandboxTradeTickListResponse(
            items=[self._to_tick_response(tick) for tick in ticks],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def list_orders(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> SandboxTradeOrderListResponse:
        """List sandbox order history for one caller-owned session."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        orders, total = await self.order_repo.list_by_session(
            session_id=session.id,
            page=page,
            page_size=page_size,
        )
        return SandboxTradeOrderListResponse(
            items=[self._to_order_response(order) for order in orders],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def list_settlements(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> SandboxTradeSettlementListResponse:
        """List settlement history for one caller-owned session."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        settlements, total = await self.settlement_repo.list_by_session(
            session_id=session.id,
            page=page,
            page_size=page_size,
        )
        return SandboxTradeSettlementListResponse(
            items=[
                self._to_settlement_response(settlement)
                for settlement in settlements
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def list_portfolio_snapshots(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> SandboxTradePortfolioSnapshotListResponse:
        """List portfolio snapshots for one caller-owned session."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        snapshots, total = await self.snapshot_repo.list_by_session(
            session_id=session.id,
            page=page,
            page_size=page_size,
        )
        return SandboxTradePortfolioSnapshotListResponse(
            items=[self._to_snapshot_response(snapshot) for snapshot in snapshots],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_portfolio_state(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
    ) -> SandboxTradePortfolioStateResponse:
        """Read current position, latest snapshot, and pending settlements."""
        session = await self._get_owned_session(
            current_user=current_user,
            organization_id=organization_id,
            session_id=session_id,
        )
        position = await self.position_repo.find_by_session(session_id=session.id)
        if position is None:
            raise SandboxTradeSessionNotFoundError("Sandbox trade position not found")
        latest_snapshot = await self.snapshot_repo.find_latest_by_session(
            session_id=session.id
        )
        pending_settlements = await self.settlement_repo.list_pending_by_session(
            session_id=session.id
        )
        return SandboxTradePortfolioStateResponse(
            position=self._to_position_response(position),
            latest_snapshot=(
                None
                if latest_snapshot is None
                else self._to_snapshot_response(latest_snapshot)
            ),
            pending_settlements=[
                self._to_settlement_response(settlement)
                for settlement in pending_settlements
            ],
        )

    async def _get_owned_session(
        self,
        *,
        current_user: User,
        organization_id: str,
        session_id: str,
    ) -> SandboxTradeSession:
        session = await self.session_repo.find_owned_session(
            session_id=session_id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        if session is None:
            raise SandboxTradeSessionNotFoundError()
        return session

    async def _ensure_symbol_exists(self, symbol: str) -> None:
        if not await self.stock_repo.exists_by_symbol(symbol):
            raise StockSymbolNotFoundError()

    async def _set_session_status(
        self,
        *,
        session: SandboxTradeSession,
        current_user: User,
        organization_id: str,
        status: SandboxTradeSessionStatus,
        next_run_at: datetime | None = None,
    ) -> SandboxTradeSession:
        updated = await self.session_repo.update_owned_session(
            session_id=session.id,
            user_id=current_user.id,
            organization_id=organization_id,
            status=status,
            next_run_at=next_run_at if next_run_at is not None else session.next_run_at,
        )
        if updated is None:
            raise SandboxTradeSessionNotFoundError()
        return updated

    @staticmethod
    def _ensure_mutable(session: SandboxTradeSession) -> None:
        if session.status == SandboxTradeSessionStatus.STOPPED:
            raise InvalidSandboxTradeSessionStateError(
                "Stopped sandbox trade sessions cannot be updated"
            )

    @staticmethod
    def _to_runtime_config_model(
        request: object,
    ) -> SandboxTradeAgentRuntimeConfig | None:
        if request is None:
            return None
        return SandboxTradeAgentRuntimeConfig(
            provider=request.provider,
            model=request.model,
            reasoning=request.reasoning,
        )

    @classmethod
    def _to_session_response(
        cls,
        session: SandboxTradeSession,
    ) -> SandboxTradeSessionResponse:
        summary = cls._to_session_summary(session)
        return SandboxTradeSessionResponse(**summary.model_dump())

    @staticmethod
    def _to_session_summary(
        session: SandboxTradeSession,
    ) -> SandboxTradeSessionSummary:
        return SandboxTradeSessionSummary(
            id=session.id,
            symbol=session.symbol,
            status=session.status,
            initial_capital=session.initial_capital,
            next_run_at=session.next_run_at,
            last_tick_at=session.last_tick_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
            runtime_config=(
                None
                if session.runtime_config is None
                else SandboxTradeAgentRuntimeConfigResponse(
                    provider=session.runtime_config.provider,
                    model=session.runtime_config.model,
                    reasoning=session.runtime_config.reasoning,
                )
            ),
        )

    @staticmethod
    def _to_lifecycle_response(
        session: SandboxTradeSession,
    ) -> SandboxTradeSessionLifecycleResponse:
        return SandboxTradeSessionLifecycleResponse(
            id=session.id,
            status=session.status,
            updated_at=session.updated_at,
        )

    @staticmethod
    def _to_tick_response(tick: SandboxTradeTick) -> SandboxTradeTickResponse:
        return SandboxTradeTickResponse(
            id=tick.id,
            session_id=tick.session_id,
            tick_at=tick.tick_at,
            status=tick.status,
            started_at=tick.started_at,
            completed_at=tick.completed_at,
            market_snapshot=(
                None
                if tick.market_snapshot is None
                else SandboxTradeMarketSnapshotResponse(
                    symbol=tick.market_snapshot.symbol,
                    source=tick.market_snapshot.source,
                    latest_price=tick.market_snapshot.latest_price,
                    observed_at=tick.market_snapshot.observed_at,
                    summary=tick.market_snapshot.summary,
                )
            ),
            decision=(
                None
                if tick.decision is None
                else SandboxTradeDecisionResponse(
                    action=tick.decision.action,
                    quantity_type=tick.decision.quantity_type,
                    quantity_value=tick.decision.quantity_value,
                    reason=tick.decision.reason,
                    confidence=tick.decision.confidence,
                    risk_notes=tick.decision.risk_notes,
                )
            ),
            order_id=tick.order_id,
            skip_reason=tick.skip_reason,
            rejection_reason=tick.rejection_reason,
            error=tick.error,
            created_at=tick.created_at,
            updated_at=tick.updated_at,
        )

    @staticmethod
    def _to_order_response(order: SandboxTradeOrder) -> SandboxTradeOrderResponse:
        return SandboxTradeOrderResponse(
            id=order.id,
            session_id=order.session_id,
            tick_id=order.tick_id,
            symbol=order.symbol,
            side=order.side,
            status=order.status,
            quantity=order.quantity,
            price=order.price,
            gross_amount=order.gross_amount,
            rejection_reason=order.rejection_reason,
            filled_at=order.filled_at,
            trade_date=order.trade_date,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _to_position_response(
        position: SandboxTradePosition,
    ) -> SandboxTradePositionResponse:
        return SandboxTradePositionResponse(
            session_id=position.session_id,
            symbol=position.symbol,
            available_cash=position.available_cash,
            pending_cash=position.pending_cash,
            total_quantity=position.total_quantity,
            sellable_quantity=position.sellable_quantity,
            pending_quantity=position.pending_quantity,
            average_cost=position.average_cost,
            realized_pnl=position.realized_pnl,
            created_at=position.created_at,
            updated_at=position.updated_at,
        )

    @staticmethod
    def _to_settlement_response(
        settlement: SandboxTradeSettlement,
    ) -> SandboxTradeSettlementResponse:
        return SandboxTradeSettlementResponse(
            id=settlement.id,
            session_id=settlement.session_id,
            order_id=settlement.order_id,
            symbol=settlement.symbol,
            asset_type=settlement.asset_type,
            status=settlement.status,
            amount=settlement.amount,
            quantity=settlement.quantity,
            trade_date=settlement.trade_date,
            settle_at=settlement.settle_at,
            settled_at=settlement.settled_at,
            created_at=settlement.created_at,
            updated_at=settlement.updated_at,
        )

    @staticmethod
    def _to_snapshot_response(
        snapshot: SandboxTradePortfolioSnapshot,
    ) -> SandboxTradePortfolioSnapshotResponse:
        return SandboxTradePortfolioSnapshotResponse(
            id=snapshot.id,
            session_id=snapshot.session_id,
            tick_id=snapshot.tick_id,
            symbol=snapshot.symbol,
            available_cash=snapshot.available_cash,
            pending_cash=snapshot.pending_cash,
            total_quantity=snapshot.total_quantity,
            sellable_quantity=snapshot.sellable_quantity,
            pending_quantity=snapshot.pending_quantity,
            latest_price=snapshot.latest_price,
            market_value=snapshot.market_value,
            equity=snapshot.equity,
            realized_pnl=snapshot.realized_pnl,
            unrealized_pnl=snapshot.unrealized_pnl,
            created_at=snapshot.created_at,
        )


def _default_next_run_at() -> datetime:
    """Return a placeholder due time until trading-window scheduling is added."""
    return datetime.now(timezone.utc)
