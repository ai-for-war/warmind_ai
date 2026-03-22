"""Worker for meeting utterance persistence and incremental note generation."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from pydantic import ValidationError

from app.config.settings import get_settings
from app.domain.schemas.meeting import (
    MeetingNoteTask,
    MeetingNoteTerminalTask,
    parse_meeting_note_task,
)
from app.infrastructure.database.mongodb import MongoDB
from app.infrastructure.redis.client import RedisClient
from app.infrastructure.redis.redis_queue import RedisQueue
from app.repo.meeting_note_chunk_repo import MeetingNoteChunkRepository
from app.repo.meeting_utterance_repo import MeetingUtteranceRepository
from app.services.meeting.note_generation_service import MeetingNoteGenerationService
from app.services.meeting.note_processing_service import (
    MeetingNoteProcessingResult,
    MeetingNoteProcessingService,
)
from app.services.meeting.note_state_store import RedisMeetingNoteStateStore

logger = logging.getLogger(__name__)


class MeetingNoteWorker:
    """Consume queued meeting note tasks and process them asynchronously."""

    MAX_RETRIES = 3
    DEQUEUE_TIMEOUT = 5

    def __init__(self) -> None:
        self.settings = get_settings()
        self.running = False
        self._queue: RedisQueue | None = None
        self._processor: MeetingNoteProcessingService | None = None

    @property
    def queue(self) -> RedisQueue:
        if self._queue is None:
            self._queue = RedisQueue(RedisClient.get_client())
        return self._queue

    @property
    def processor(self) -> MeetingNoteProcessingService:
        if self._processor is None:
            db = MongoDB.get_db()
            self._processor = MeetingNoteProcessingService(
                note_state_store=RedisMeetingNoteStateStore(RedisClient.get_client()),
                utterance_repo=MeetingUtteranceRepository(db),
                note_chunk_repo=MeetingNoteChunkRepository(db),
                note_generation_service=MeetingNoteGenerationService(),
            )
        return self._processor

    async def process_task(self, task: MeetingNoteTask) -> MeetingNoteProcessingResult:
        """Process one validated meeting note task payload."""
        result = await self.processor.process_task(task)
        if result.summary_deferred:
            logger.info(
                "Deferred meeting note task kind=%s meeting_id=%s because the "
                "summary lock is busy",
                task.kind,
                task.meeting_id,
            )
            return result

        logger.info(
            "Processed meeting note task kind=%s meeting_id=%s created_chunks=%d",
            task.kind,
            task.meeting_id,
            len(result.created_chunks),
        )
        return result

    async def handle_deferred_task(self, task: MeetingNoteTask) -> None:
        """Requeue one task when summary work was deferred due to lock contention."""
        requeued_task = task.model_copy(update={"queued_at": None})
        enqueued = await self.queue.enqueue(
            queue_name=self.settings.MEETING_NOTE_QUEUE_NAME,
            data=requeued_task.model_dump(mode="json", exclude_none=True),
        )
        if not enqueued:
            raise RuntimeError(
                "Failed to requeue meeting note task after summary lock contention"
            )

        logger.info(
            "Re-queued meeting note task kind=%s meeting_id=%s after summary "
            "lock contention",
            task.kind,
            task.meeting_id,
        )

    async def handle_failed_task(
        self,
        task: MeetingNoteTask,
        error_message: str,
    ) -> None:
        """Requeue one failed task until the retry budget is exhausted."""
        if task.retry_count >= self.MAX_RETRIES:
            logger.error(
                "Meeting note task failed after %d retries kind=%s meeting_id=%s: %s",
                self.MAX_RETRIES,
                task.kind,
                task.meeting_id,
                error_message,
            )
            return

        retry_task = task.model_copy(
            update={
                "retry_count": task.retry_count + 1,
                "queued_at": None,
            }
        )
        await self.queue.enqueue(
            queue_name=self.settings.MEETING_NOTE_QUEUE_NAME,
            data=retry_task.model_dump(mode="json", exclude_none=True),
        )
        logger.warning(
            "Re-queued meeting note task kind=%s meeting_id=%s retry=%d/%d: %s",
            task.kind,
            task.meeting_id,
            retry_task.retry_count,
            self.MAX_RETRIES,
            error_message,
        )

    async def run_once(self) -> bool:
        """Process one queue item if available."""
        task_data = await self.queue.dequeue(
            queue_name=self.settings.MEETING_NOTE_QUEUE_NAME,
            timeout=self.DEQUEUE_TIMEOUT,
        )
        if task_data is None:
            return False

        try:
            task = parse_meeting_note_task(task_data)
        except ValidationError:
            logger.exception("Discarding invalid meeting note task payload: %s", task_data)
            return True

        try:
            result = await self.process_task(task)
            if result.summary_deferred and isinstance(task, MeetingNoteTerminalTask):
                await self.handle_deferred_task(task)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed processing meeting note task kind=%s meeting_id=%s",
                task.kind,
                task.meeting_id,
            )
            await self.handle_failed_task(task, str(exc))

        return True

    async def start(self) -> None:
        """Run the worker loop until stop is requested."""
        self.running = True
        logger.info("Meeting note worker started")

        while self.running:
            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error in meeting note worker loop: %s", exc)
                await asyncio.sleep(1)

        logger.info("Meeting note worker stopped")

    def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping meeting note worker...")
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

    worker = MeetingNoteWorker()

    def signal_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
        logger.info("Received signal %s, initiating shutdown...", signum)
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await setup_connections()
        await worker.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Meeting note worker failed: %s", exc)
        sys.exit(1)
    finally:
        await cleanup_connections()


if __name__ == "__main__":
    asyncio.run(main())
