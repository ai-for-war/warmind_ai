"""Portfolio snapshot persistence for sandbox trade-agent ticks."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.models.sandbox_trade_agent import (
    SandboxTradePortfolioSnapshot,
    SandboxTradePosition,
    SandboxTradeSession,
    SandboxTradeTick,
)
from app.repo.sandbox_trade_agent_repo import (
    SandboxTradePortfolioSnapshotRepository,
    SandboxTradePositionRepository,
)


class SandboxTradePortfolioSnapshotService:
    """Persist append-only portfolio snapshots after terminal tick states."""

    def __init__(
        self,
        *,
        position_repo: SandboxTradePositionRepository,
        snapshot_repo: SandboxTradePortfolioSnapshotRepository,
    ) -> None:
        self.position_repo = position_repo
        self.snapshot_repo = snapshot_repo

    async def persist_for_tick(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        position: SandboxTradePosition | None = None,
        latest_price: float | None = None,
        now: datetime | None = None,
    ) -> SandboxTradePortfolioSnapshot | None:
        """Persist the current portfolio accounting state for one terminal tick."""
        if session.id is None:
            return None
        current_position = position or await self.position_repo.find_by_session(
            session_id=session.id
        )
        if current_position is None:
            return None

        snapshot_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        price = self._resolve_latest_price(tick=tick, explicit_price=latest_price)
        market_value = (
            current_position.total_quantity * price if price is not None else 0
        )
        unrealized_pnl = (
            (price - current_position.average_cost) * current_position.total_quantity
            if price is not None and current_position.total_quantity > 0
            else None
        )
        equity = (
            current_position.available_cash
            + current_position.pending_cash
            + market_value
        )

        return await self.snapshot_repo.create(
            session_id=session.id,
            tick_id=tick.id,
            symbol=current_position.symbol,
            available_cash=current_position.available_cash,
            pending_cash=current_position.pending_cash,
            total_quantity=current_position.total_quantity,
            sellable_quantity=current_position.sellable_quantity,
            pending_quantity=current_position.pending_quantity,
            latest_price=price,
            market_value=market_value,
            equity=equity,
            realized_pnl=current_position.realized_pnl,
            unrealized_pnl=unrealized_pnl,
            created_at=snapshot_at,
        )

    @staticmethod
    def _resolve_latest_price(
        *,
        tick: SandboxTradeTick,
        explicit_price: float | None,
    ) -> float | None:
        if explicit_price is not None:
            return explicit_price
        if tick.market_snapshot is None:
            return None
        return tick.market_snapshot.latest_price
