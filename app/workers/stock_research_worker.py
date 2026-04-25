"""Worker for processing queued stock research reports from Redis."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from pydantic import ValidationError

from app.agents.implementations.stock_research_agent.runtime import (
    StockResearchAgentRuntimeConfig,
)
from app.common.repo import get_stock_research_report_repo
from app.common.service import get_redis_queue, get_stock_research_service
from app.config.settings import get_settings
from app.domain.schemas.stock_research_task import (
    StockResearchTask,
    parse_stock_research_task,
)
from app.infrastructure.database.mongodb import MongoDB
from app.infrastructure.redis.client import RedisClient
from app.infrastructure.redis.redis_queue import RedisQueue
from app.repo.stock_research_report_repo import StockResearchReportRepository
from app.services.stocks.stock_research_service import StockResearchService

logger = logging.getLogger(__name__)


class StockResearchWorker:
    """Consume stock research tasks and run persisted report lifecycles."""

    DEQUEUE_TIMEOUT = 5

    def __init__(self) -> None:
        self.settings = get_settings()
        self.running = False
        self.max_concurrency = max(1, int(self.settings.STOCK_RESEARCH_MAX_CONCURRENCY))
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._active_tasks: set[asyncio.Task[Any]] = set()
        self._queue: RedisQueue | None = None
        self._report_repo: StockResearchReportRepository | None = None
        self._service: StockResearchService | None = None

    @property
    def queue(self) -> RedisQueue:
        if self._queue is None:
            self._queue = get_redis_queue()
        return self._queue

    @property
    def report_repo(self) -> StockResearchReportRepository:
        if self._report_repo is None:
            self._report_repo = get_stock_research_report_repo()
        return self._report_repo

    @property
    def service(self) -> StockResearchService:
        if self._service is None:
            self._service = get_stock_research_service()
        return self._service

    async def process_task(self, task: StockResearchTask) -> bool:
        """Claim and process one validated stock research task."""
        claimed = await self.report_repo.claim_queued_report(task.report_id)
        if claimed is None:
            existing = await self.report_repo.find_by_id(task.report_id)
            if existing is None:
                logger.info("Skip stock research task %s: report not found", task.report_id)
                return False

            logger.info(
                "Skip stock research task %s: report status is %s",
                task.report_id,
                existing.status,
            )
            return False

        runtime_config = StockResearchAgentRuntimeConfig(
            provider=task.runtime_config.provider,
            model=task.runtime_config.model,
            reasoning=task.runtime_config.reasoning,
        )
        await self.service.process_report(
            report_id=claimed.id or task.report_id,
            symbol=claimed.symbol,
            runtime_config=runtime_config,
        )
        logger.info(
            "Processed stock research task report_id=%s symbol=%s",
            task.report_id,
            claimed.symbol,
        )
        return True

    async def run_once(self) -> bool:
        """Dispatch one queue item into the worker pool if capacity is available."""
        await self._semaphore.acquire()
        dispatched = False
        try:
            task_data = await self.queue.dequeue(
                queue_name=self.settings.STOCK_RESEARCH_QUEUE_NAME,
                timeout=self.DEQUEUE_TIMEOUT,
            )
            if task_data is None:
                return False

            try:
                task = parse_stock_research_task(task_data)
            except ValidationError:
                logger.exception(
                    "Discarding invalid stock research task payload: %s",
                    task_data,
                )
                return True

            active_task = asyncio.create_task(self._run_task(task))
            self._active_tasks.add(active_task)
            dispatched = True
            return True
        finally:
            if not dispatched:
                self._semaphore.release()

    async def _run_task(self, task: StockResearchTask) -> None:
        """Run one queued task and release its concurrency slot."""
        current_task = asyncio.current_task()
        try:
            await self.process_task(task)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed processing stock research task report_id=%s: %s",
                task.report_id,
                exc,
            )
        finally:
            if current_task is not None:
                self._active_tasks.discard(current_task)
            self._semaphore.release()

    async def _wait_for_active_tasks(self) -> None:
        """Wait for all in-flight stock research tasks during shutdown."""
        if not self._active_tasks:
            return

        logger.info(
            "Waiting for %d active stock research task(s) to finish",
            len(self._active_tasks),
        )
        await asyncio.gather(*list(self._active_tasks), return_exceptions=True)

    async def start(self) -> None:
        """Run the worker loop until stop is requested."""
        self.running = True
        logger.info(
            "Stock research worker started with max_concurrency=%d",
            self.max_concurrency,
        )

        try:
            while self.running:
                try:
                    await self.run_once()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error in stock research worker loop: %s", exc)
                    await asyncio.sleep(1)
        finally:
            await self._wait_for_active_tasks()

        logger.info("Stock research worker stopped")

    def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping stock research worker...")
        self.running = False


async def setup_connections() -> None:
    """Initialize MongoDB and Redis for the worker process."""
    settings = get_settings()

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

    worker = StockResearchWorker()

    def signal_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
        logger.info("Received signal %s, initiating shutdown...", signum)
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await setup_connections()
        await worker.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Stock research worker failed: %s", exc)
        sys.exit(1)
    finally:
        await cleanup_connections()


if __name__ == "__main__":
    asyncio.run(main())
