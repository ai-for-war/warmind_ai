"""Queue helper for sandbox trade-agent tick execution tasks."""

from __future__ import annotations

from datetime import datetime

from app.domain.models.sandbox_trade_agent import SandboxTradeSession, SandboxTradeTick
from app.domain.schemas.sandbox_trade_task import SandboxTradeTickTask
from app.infrastructure.redis.redis_queue import RedisQueue

DEFAULT_SANDBOX_TRADE_AGENT_QUEUE_NAME = "sandbox_trade_agent_tasks"


class SandboxTradeQueueService:
    """Build and enqueue sandbox trade-agent worker task payloads."""

    def __init__(
        self,
        *,
        queue: RedisQueue,
        queue_name: str = DEFAULT_SANDBOX_TRADE_AGENT_QUEUE_NAME,
    ) -> None:
        self.queue = queue
        self.queue_name = queue_name

    async def enqueue_tick(
        self,
        *,
        session_id: str,
        tick_id: str,
        lock_token: str,
        symbol: str,
        tick_at: datetime,
    ) -> bool:
        """Enqueue one claimed sandbox trade tick for worker execution."""
        task = SandboxTradeTickTask(
            session_id=session_id,
            tick_id=tick_id,
            lock_token=lock_token,
            symbol=symbol,
            tick_at=tick_at,
        )
        return await self.queue.enqueue(
            self.queue_name,
            task.model_dump(mode="json", exclude_none=True),
        )

    async def enqueue_tick_model(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
    ) -> bool:
        """Enqueue one tick model when both session and tick ids are present."""
        if session.id is None or tick.id is None or tick.lock_token is None:
            return False
        return await self.enqueue_tick(
            session_id=session.id,
            tick_id=tick.id,
            lock_token=tick.lock_token,
            symbol=session.symbol,
            tick_at=tick.tick_at,
        )
