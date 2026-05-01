"""Worker for sandbox trade-agent dispatch and tick execution."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from app.common.repo import (
    get_sandbox_trade_position_repo,
    get_sandbox_trade_session_repo,
    get_sandbox_trade_settlement_repo,
    get_sandbox_trade_tick_repo,
)
from app.common.service import (
    get_redis_queue,
    get_sandbox_trade_agent_dispatcher_service,
    get_sandbox_trade_agent_runtime_service,
    get_sandbox_trade_execution_service,
    get_sandbox_trade_market_data_service,
    get_sandbox_trade_portfolio_snapshot_service,
)
from app.config.langsmith import configure_langsmith
from app.config.settings import get_settings
from app.domain.models.sandbox_trade_agent import (
    SandboxTradePosition,
    SandboxTradeSession,
    SandboxTradeSessionStatus,
    SandboxTradeTick,
    SandboxTradeTickStatus,
)
from app.domain.schemas.sandbox_trade_task import (
    SandboxTradeTickTask,
    parse_sandbox_trade_tick_task,
)
from app.infrastructure.database.mongodb import MongoDB
from app.infrastructure.redis.client import RedisClient
from app.infrastructure.redis.redis_queue import RedisQueue
from app.repo.sandbox_trade_agent_repo import (
    SandboxTradePositionRepository,
    SandboxTradeSessionRepository,
    SandboxTradeSettlementRepository,
    SandboxTradeTickRepository,
)
from app.services.stocks.sandbox_trade_agent_runtime_service import (
    SandboxTradeAgentRuntimeService,
)
from app.services.stocks.sandbox_trade_dispatcher_service import (
    SandboxTradeAgentDispatcherService,
)
from app.services.stocks.sandbox_trade_execution_service import (
    SandboxTradeExecutionService,
)
from app.services.stocks.sandbox_trade_market_data_service import (
    SandboxTradeMarketDataService,
)
from app.services.stocks.sandbox_trade_portfolio_snapshot_service import (
    SandboxTradePortfolioSnapshotService,
)
from app.services.stocks.sandbox_trade_schedule_calculator import (
    calculate_next_sandbox_trade_run_at,
    parse_sandbox_trade_trading_windows,
)

logger = logging.getLogger(__name__)

SESSION_NOT_ACTIVE = "SESSION_NOT_ACTIVE"
SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
POSITION_NOT_FOUND = "POSITION_NOT_FOUND"


class SandboxTradeAgentWorker:
    """Dispatch due sandbox sessions and process queued tick tasks."""

    DEQUEUE_TIMEOUT = 5

    def __init__(self) -> None:
        self.settings = get_settings()
        self.running = False
        self._queue: RedisQueue | None = None
        self._session_repo: SandboxTradeSessionRepository | None = None
        self._tick_repo: SandboxTradeTickRepository | None = None
        self._position_repo: SandboxTradePositionRepository | None = None
        self._settlement_repo: SandboxTradeSettlementRepository | None = None
        self._dispatcher: SandboxTradeAgentDispatcherService | None = None
        self._market_data_service: SandboxTradeMarketDataService | None = None
        self._runtime_service: SandboxTradeAgentRuntimeService | None = None
        self._execution_service: SandboxTradeExecutionService | None = None
        self._snapshot_service: SandboxTradePortfolioSnapshotService | None = None
        self._last_dispatch_monotonic: float | None = None

    @property
    def queue(self) -> RedisQueue:
        if self._queue is None:
            self._queue = get_redis_queue()
        return self._queue

    @property
    def session_repo(self) -> SandboxTradeSessionRepository:
        if self._session_repo is None:
            self._session_repo = get_sandbox_trade_session_repo()
        return self._session_repo

    @property
    def tick_repo(self) -> SandboxTradeTickRepository:
        if self._tick_repo is None:
            self._tick_repo = get_sandbox_trade_tick_repo()
        return self._tick_repo

    @property
    def position_repo(self) -> SandboxTradePositionRepository:
        if self._position_repo is None:
            self._position_repo = get_sandbox_trade_position_repo()
        return self._position_repo

    @property
    def settlement_repo(self) -> SandboxTradeSettlementRepository:
        if self._settlement_repo is None:
            self._settlement_repo = get_sandbox_trade_settlement_repo()
        return self._settlement_repo

    @property
    def dispatcher(self) -> SandboxTradeAgentDispatcherService:
        if self._dispatcher is None:
            self._dispatcher = get_sandbox_trade_agent_dispatcher_service()
        return self._dispatcher

    @property
    def market_data_service(self) -> SandboxTradeMarketDataService:
        if self._market_data_service is None:
            self._market_data_service = get_sandbox_trade_market_data_service()
        return self._market_data_service

    @property
    def runtime_service(self) -> SandboxTradeAgentRuntimeService:
        if self._runtime_service is None:
            self._runtime_service = get_sandbox_trade_agent_runtime_service()
        return self._runtime_service

    @property
    def execution_service(self) -> SandboxTradeExecutionService:
        if self._execution_service is None:
            self._execution_service = get_sandbox_trade_execution_service()
        return self._execution_service

    @property
    def snapshot_service(self) -> SandboxTradePortfolioSnapshotService:
        if self._snapshot_service is None:
            self._snapshot_service = get_sandbox_trade_portfolio_snapshot_service()
        return self._snapshot_service

    async def dispatch_due_if_needed(self) -> None:
        """Run the due-session dispatcher at the configured polling interval."""
        poll_interval = max(
            1,
            int(self.settings.SANDBOX_TRADE_AGENT_WORKER_POLL_INTERVAL_SECONDS),
        )
        current = time.monotonic()
        if (
            self._last_dispatch_monotonic is not None
            and current - self._last_dispatch_monotonic < poll_interval
        ):
            return

        self._last_dispatch_monotonic = current
        result = await self.dispatcher.dispatch_due()
        logger.info(
            "Sandbox trade dispatch scanned=%d dispatched=%d recovered=%d "
            "skipped=%d enqueue_failed=%d",
            result.scanned,
            result.dispatched,
            result.recovered,
            result.skipped,
            result.enqueue_failed,
        )

    async def process_task(self, task: SandboxTradeTickTask) -> bool:
        """Claim and process one validated sandbox trade-agent tick task."""
        process_now = datetime.now(timezone.utc)
        claimed_tick = await self.tick_repo.claim_for_processing(
            tick_id=task.tick_id,
            lock_token=task.lock_token,
            now=process_now,
            lock_expires_at=process_now
            + timedelta(seconds=self.settings.SANDBOX_TRADE_AGENT_TICK_LOCK_SECONDS),
        )
        if claimed_tick is None:
            logger.info(
                "Skip sandbox trade task tick_id=%s: claim failed",
                task.tick_id,
            )
            return False

        session: SandboxTradeSession | None = None
        position: SandboxTradePosition | None = None
        try:
            session = await self.session_repo.find_by_id(session_id=task.session_id)
            if session is None:
                await self._mark_failed_without_session(
                    tick=claimed_tick,
                    error=SESSION_NOT_FOUND,
                )
                return False

            if session.status != SandboxTradeSessionStatus.ACTIVE:
                position = await self.position_repo.find_by_session(
                    session_id=session.id
                )
                await self.execution_service.record_failed_tick(
                    session=session,
                    tick=claimed_tick,
                    position=position,
                    error=SESSION_NOT_ACTIVE,
                    now=process_now,
                )
                return False

            position = await self.execution_service.apply_due_settlements(
                session=session,
                now=process_now,
            )
            if position is None:
                await self.execution_service.record_failed_tick(
                    session=session,
                    tick=claimed_tick,
                    position=None,
                    error=POSITION_NOT_FOUND,
                    now=process_now,
                )
                await self._advance_session_after_terminal_tick(
                    session=session,
                    tick=claimed_tick,
                )
                return False

            prepared = await self.market_data_service.prepare_tick_market_data(
                session=session,
                tick=claimed_tick,
                now=process_now,
            )
            if not prepared.should_continue:
                await self._advance_session_after_terminal_tick(
                    session=session,
                    tick=prepared.tick,
                )
                return True

            pending_settlements = await self.settlement_repo.list_pending_by_session(
                session_id=session.id
            )
            recent_ticks, _ = await self.tick_repo.list_by_session(
                session_id=session.id,
                page=1,
                page_size=10,
            )
            latest_snapshot = (
                await self.snapshot_service.snapshot_repo.find_latest_by_session(
                    session_id=session.id
                )
            )
            decided_tick = await self.runtime_service.invoke_for_tick(
                session=session,
                tick=prepared.tick,
                position=position,
                pending_settlements=pending_settlements,
                recent_ticks=recent_ticks,
                latest_snapshot=latest_snapshot,
                now=process_now,
            )
            if decided_tick.status == SandboxTradeTickStatus.REJECTED:
                await self._advance_session_after_terminal_tick(
                    session=session,
                    tick=decided_tick,
                )
                return True

            execution = await self.execution_service.execute_tick_decision(
                session=session,
                tick=decided_tick,
                position=position,
                now=process_now,
            )
            if execution.tick.status in _TERMINAL_TICK_STATUSES:
                await self._advance_session_after_terminal_tick(
                    session=session,
                    tick=execution.tick,
                )
            logger.info(
                "Processed sandbox trade tick session_id=%s tick_id=%s status=%s",
                task.session_id,
                task.tick_id,
                execution.tick.status.value,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed processing sandbox trade task session_id=%s tick_id=%s: %s",
                task.session_id,
                task.tick_id,
                exc,
            )
            if session is None:
                await self._mark_failed_without_session(
                    tick=claimed_tick,
                    error=str(exc),
                )
                return False

            failed_tick = await self.execution_service.record_failed_tick(
                session=session,
                tick=claimed_tick,
                position=position,
                error=str(exc),
                now=datetime.now(timezone.utc),
            )
            await self._advance_session_after_terminal_tick(
                session=session,
                tick=failed_tick,
            )
            return False

    async def run_once(self) -> bool:
        """Dispatch due sessions, then process one queued tick task if available."""
        await self.dispatch_due_if_needed()
        task_data = await self.queue.dequeue(
            queue_name=self.settings.SANDBOX_TRADE_AGENT_QUEUE_NAME,
            timeout=self.DEQUEUE_TIMEOUT,
        )
        if task_data is None:
            return False

        try:
            task = parse_sandbox_trade_tick_task(task_data)
        except ValidationError:
            logger.exception(
                "Discarding invalid sandbox trade task payload: %s",
                task_data,
            )
            return True

        await self.process_task(task)
        return True

    async def start(self) -> None:
        """Run the worker loop until stop is requested."""
        self.running = True
        logger.info("Sandbox trade-agent worker started")

        while self.running:
            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error in sandbox trade-agent worker loop: %s", exc)
                await asyncio.sleep(1)

        logger.info("Sandbox trade-agent worker stopped")

    def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping sandbox trade-agent worker...")
        self.running = False

    async def _mark_failed_without_session(
        self,
        *,
        tick: SandboxTradeTick,
        error: str,
    ) -> None:
        if tick.id is None or tick.lock_token is None:
            return
        await self.tick_repo.mark_failed(
            tick_id=tick.id,
            lock_token=tick.lock_token,
            completed_at=datetime.now(timezone.utc),
            error=error,
        )

    async def _advance_session_after_terminal_tick(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
    ) -> None:
        if session.id is None:
            return

        tick_at = tick.tick_at.astimezone(timezone.utc)
        windows = parse_sandbox_trade_trading_windows(
            self.settings.SANDBOX_TRADE_AGENT_TRADING_WINDOWS
        )
        next_run_at = calculate_next_sandbox_trade_run_at(
            after=tick_at,
            cadence_seconds=self.settings.SANDBOX_TRADE_AGENT_CADENCE_SECONDS,
            windows=windows,
        )
        await self.session_repo.advance_next_run_at(
            session_id=session.id,
            expected_next_run_at=tick_at,
            next_run_at=next_run_at,
            last_tick_at=tick_at,
        )


_TERMINAL_TICK_STATUSES = {
    SandboxTradeTickStatus.COMPLETED,
    SandboxTradeTickStatus.SKIPPED,
    SandboxTradeTickStatus.REJECTED,
    SandboxTradeTickStatus.FAILED,
}


async def setup_connections() -> None:
    """Initialize MongoDB, Redis, and LangSmith for the worker process."""
    settings = get_settings()
    configure_langsmith(settings)

    await MongoDB.connect(uri=settings.MONGODB_URI, db_name=settings.MONGODB_DB_NAME)
    logger.info("Connected to MongoDB")

    await RedisClient.connect(url=settings.REDIS_URL)
    logger.info("Connected to Redis")


async def cleanup_connections() -> None:
    """Close worker database and cache connections."""
    await MongoDB.disconnect()
    logger.info("Disconnected from MongoDB")

    await RedisClient.disconnect()
    logger.info("Disconnected from Redis")


async def main() -> None:
    """Worker process entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    worker = SandboxTradeAgentWorker()

    def signal_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
        logger.info("Received signal %s, initiating shutdown...", signum)
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await setup_connections()
        await worker.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Sandbox trade-agent worker failed: %s", exc)
        sys.exit(1)
    finally:
        await cleanup_connections()


if __name__ == "__main__":
    asyncio.run(main())
