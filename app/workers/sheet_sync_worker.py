"""Sheet Sync Worker for processing sync tasks from Redis queue.

This worker continuously dequeues sync tasks, acquires rate limit tokens,
and processes sheet synchronization with retry logic.
"""

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.common.service import get_crawler_service, get_redis_queue
from app.common.event_socket import SheetSyncEvents
from app.config.settings import get_settings
from app.infrastructure.database.mongodb import MongoDB
from app.infrastructure.google_sheets.rate_limiter import GoogleSheetsRateLimiter
from app.infrastructure.redis.client import RedisClient
from app.socket_gateway.worker_gateway import worker_gateway

logger = logging.getLogger(__name__)


@dataclass
class SyncTask:
    """Represents a sync task from the queue."""

    connection_id: str
    user_id: str
    queued_at: str
    retry_count: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncTask":
        """Create SyncTask from dictionary.

        Args:
            data: Task data dictionary

        Returns:
            SyncTask instance
        """
        return cls(
            connection_id=data["connection_id"],
            user_id=data["user_id"],
            queued_at=data.get("queued_at", datetime.now(timezone.utc).isoformat()),
            retry_count=data.get("retry_count", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for queue storage.

        Returns:
            Dictionary representation
        """
        return {
            "connection_id": self.connection_id,
            "user_id": self.user_id,
            "queued_at": self.queued_at,
            "retry_count": self.retry_count,
        }


class SheetSyncWorker:
    """Worker for processing sheet sync tasks from Redis queue.

    Implements:
    - Continuous task dequeuing from Redis
    - Rate limiting via Token Bucket
    - Retry logic with max 3 retries
    - Graceful shutdown handling
    """

    # Each sync makes approximately 2 API requests (headers + data)
    REQUESTS_PER_SYNC = 2
    MAX_RETRIES = 3
    # Blocking timeout for dequeue (seconds)
    DEQUEUE_TIMEOUT = 5

    def __init__(self):
        """Initialize SheetSyncWorker."""
        self.settings = get_settings()
        self.rate_limiter = GoogleSheetsRateLimiter()
        self.running = False
        self._queue: Optional[Any] = None
        self._crawler_service: Optional[Any] = None

    @property
    def queue(self):
        """Get Redis queue instance (lazy initialization)."""
        if self._queue is None:
            self._queue = get_redis_queue()
        return self._queue

    @property
    def crawler_service(self):
        """Get crawler service instance (lazy initialization)."""
        if self._crawler_service is None:
            self._crawler_service = get_crawler_service()
        return self._crawler_service

    async def _notify_max_retries_exceeded(
        self,
        task: SyncTask,
        error_message: str,
    ) -> None:
        """Notify user that sync failed after max retries.

        Args:
            task: The failed sync task
            error_message: Error description
        """
        await worker_gateway.emit_to_user(
            user_id=task.user_id,
            event=SheetSyncEvents.FAILED,
            data={
                "connection_id": task.connection_id,
                "error": f"Sync failed after {self.MAX_RETRIES} retries: {error_message}",
            },
        )

    async def process_task(self, task: SyncTask) -> bool:
        """Process a single sync task.

        Args:
            task: Sync task to process

        Returns:
            True if successful, False if failed
        """
        logger.info(
            "Processing sync task for connection %s (retry %d/%d)",
            task.connection_id,
            task.retry_count,
            self.MAX_RETRIES,
        )

        try:
            result = await self.crawler_service.sync_sheet(
                connection_id=task.connection_id,
                user_id=task.user_id,
            )

            if result.success:
                logger.info(
                    "Sync completed for connection %s: %d rows synced",
                    task.connection_id,
                    result.rows_synced,
                )
                return True
            else:
                logger.warning(
                    "Sync failed for connection %s: %s",
                    task.connection_id,
                    result.error_message,
                )
                return False

        except Exception as e:
            logger.exception(
                "Error processing sync task for connection %s",
                task.connection_id,
            )
            return False

    async def handle_failed_task(
        self,
        task: SyncTask,
        error_message: str = "Unknown error",
    ) -> None:
        """Handle a failed task with retry logic.

        Re-queues the task if retry count < MAX_RETRIES,
        otherwise marks as failed and notifies user.

        Args:
            task: The failed sync task
            error_message: Error description
        """
        if task.retry_count < self.MAX_RETRIES:
            # Re-queue with incremented retry count
            task.retry_count += 1
            await self.queue.enqueue(
                queue_name=self.settings.SHEET_SYNC_QUEUE_NAME,
                data=task.to_dict(),
            )
            logger.info(
                "Re-queued task for connection %s (retry %d/%d)",
                task.connection_id,
                task.retry_count,
                self.MAX_RETRIES,
            )
        else:
            # Max retries exceeded
            logger.error(
                "Max retries exceeded for connection %s",
                task.connection_id,
            )
            await self._notify_max_retries_exceeded(task, error_message)

    async def run_once(self) -> bool:
        """Run a single iteration of the worker loop.

        Returns:
            True if a task was processed, False if no task available
        """
        # Dequeue task with blocking timeout
        task_data = await self.queue.dequeue(
            queue_name=self.settings.SHEET_SYNC_QUEUE_NAME,
            timeout=self.DEQUEUE_TIMEOUT,
        )

        if task_data is None:
            return False

        task = SyncTask.from_dict(task_data)

        # Acquire rate limit tokens before processing
        # This blocks until tokens are available
        logger.debug(
            "Acquiring %d rate limit tokens for connection %s",
            self.REQUESTS_PER_SYNC,
            task.connection_id,
        )
        await self.rate_limiter.acquire(self.REQUESTS_PER_SYNC)

        # Process the task
        success = await self.process_task(task)

        if not success:
            await self.handle_failed_task(task)

        return True

    async def start(self) -> None:
        """Start the worker main loop.

        Continuously dequeues and processes tasks until stopped.
        """
        self.running = True
        logger.info("Sheet sync worker started")

        while self.running:
            try:
                await self.run_once()
            except Exception as e:
                logger.exception("Error in worker loop: %s", e)
                # Brief pause before retrying to avoid tight error loops
                await asyncio.sleep(1)

        logger.info("Sheet sync worker stopped")

    def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping sheet sync worker...")
        self.running = False


async def setup_connections() -> None:
    """Initialize database and Redis connections."""
    settings = get_settings()

    # Connect to MongoDB
    await MongoDB.connect(
        uri=settings.MONGODB_URI,
        db_name=settings.MONGODB_DB_NAME,
    )
    logger.info("Connected to MongoDB")

    # Connect to Redis
    await RedisClient.connect(url=settings.REDIS_URL)
    logger.info("Connected to Redis")


async def cleanup_connections() -> None:
    """Close database and Redis connections."""
    await MongoDB.disconnect()
    logger.info("Disconnected from MongoDB")

    await RedisClient.disconnect()
    logger.info("Disconnected from Redis")


async def main() -> None:
    """Main entry point for the worker process."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    worker = SheetSyncWorker()

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Received signal %s, initiating shutdown...", signum)
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize connections
        await setup_connections()

        # Start worker
        await worker.start()

    except Exception as e:
        logger.exception("Worker failed: %s", e)
        sys.exit(1)

    finally:
        # Cleanup connections
        await cleanup_connections()


if __name__ == "__main__":
    asyncio.run(main())
