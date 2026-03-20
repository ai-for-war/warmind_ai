"""Meeting summary worker for processing queued summary jobs."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.common.event_socket import MeetingRecordEvents
from app.common.repo import (
    get_meeting_record_repo,
    get_meeting_summary_job_repo,
    get_meeting_summary_repo,
    get_meeting_transcript_repo,
)
from app.config.settings import get_settings
from app.domain.models.meeting_summary import MeetingSummary, MeetingSummaryStatus
from app.domain.models.meeting_summary_job import MeetingSummaryJobKind
from app.domain.schemas.meeting_summary import MeetingSummaryPayload
from app.infrastructure.database.mongodb import MongoDB
from app.infrastructure.redis.client import RedisClient
from app.infrastructure.redis.redis_queue import RedisQueue
from app.repo.meeting_summary_job_repo import MeetingSummaryJobRepository
from app.socket_gateway.worker_gateway import worker_gateway
from app.services.meeting.summary_service import MeetingSummaryService

logger = logging.getLogger(__name__)


@dataclass
class MeetingSummaryTask:
    """Represents one queued meeting summary task."""

    job_id: str
    meeting_id: str
    organization_id: str
    user_id: str
    job_kind: str
    target_block_sequence: int
    queued_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MeetingSummaryTask":
        """Create a task from queue payload data."""
        return cls(
            job_id=data["job_id"],
            meeting_id=data["meeting_id"],
            organization_id=data["organization_id"],
            user_id=data["user_id"],
            job_kind=data["job_kind"],
            target_block_sequence=int(data["target_block_sequence"]),
            queued_at=data.get("queued_at", datetime.now(timezone.utc).isoformat()),
        )


class MeetingSummaryWorker:
    """Worker consuming queued meeting summary jobs."""

    DEQUEUE_TIMEOUT = 5

    def __init__(self) -> None:
        self.settings = get_settings()
        self.running = False
        self.max_concurrency = max(
            1,
            int(self.settings.MEETING_SUMMARY_MAX_CONCURRENCY),
        )
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._active_tasks: set[asyncio.Task[Any]] = set()
        self._queue: Optional[RedisQueue] = None
        self._job_repo: Optional[MeetingSummaryJobRepository] = None
        self._summary_service: Optional[MeetingSummaryService] = None

    @property
    def queue(self) -> RedisQueue:
        if self._queue is None:
            self._queue = RedisQueue(RedisClient.get_client())
        return self._queue

    @property
    def job_repo(self) -> MeetingSummaryJobRepository:
        if self._job_repo is None:
            self._job_repo = get_meeting_summary_job_repo()
        return self._job_repo

    @property
    def summary_service(self) -> MeetingSummaryService:
        if self._summary_service is None:
            self._summary_service = MeetingSummaryService(
                meeting_summary_repo=get_meeting_summary_repo(),
                meeting_summary_job_repo=get_meeting_summary_job_repo(),
                meeting_transcript_repo=get_meeting_transcript_repo(),
                meeting_record_repo=get_meeting_record_repo(),
                redis_queue=self.queue,
            )
        return self._summary_service

    async def run_once(self) -> bool:
        """Dispatch a single queue item if worker capacity is available."""
        await self._semaphore.acquire()
        task_data = None
        try:
            task_data = await self.queue.dequeue(
                queue_name=self.settings.MEETING_SUMMARY_QUEUE_NAME,
                timeout=self.DEQUEUE_TIMEOUT,
            )
            if task_data is None:
                return False

            task = MeetingSummaryTask.from_dict(task_data)
            active_task = asyncio.create_task(self._run_task(task))
            self._active_tasks.add(active_task)
            return True
        finally:
            if task_data is None:
                self._semaphore.release()

    async def _run_task(self, task: MeetingSummaryTask) -> None:
        """Run one queued task and release its concurrency slot."""
        current_task = asyncio.current_task()
        try:
            await self.process_task(task)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Unhandled error while processing meeting summary task %s",
                task.job_id,
            )
        finally:
            if current_task is not None:
                self._active_tasks.discard(current_task)
            self._semaphore.release()

    async def _wait_for_active_tasks(self) -> None:
        """Wait for in-flight tasks to finish during shutdown."""
        if not self._active_tasks:
            return

        logger.info(
            "Waiting for %d active meeting summary task(s) to finish",
            len(self._active_tasks),
        )
        await asyncio.gather(*list(self._active_tasks), return_exceptions=True)

    async def process_task(self, task: MeetingSummaryTask) -> None:
        """Claim and execute one queued meeting summary job."""
        claimed = await self.job_repo.claim_pending_job(task.job_id)
        if claimed is None:
            logger.info(
                "Skip task %s: pending claim lost or job already terminal",
                task.job_id,
            )
            return

        latest_summary = await self.summary_service.get_latest_summary(
            meeting_id=claimed.meeting_id,
            organization_id=claimed.organization_id,
        )

        try:
            if self._should_emit_started_event(
                latest_summary=latest_summary,
                job_kind=claimed.job_kind,
                target_block_sequence=claimed.target_block_sequence,
            ):
                await self._emit_lifecycle_event(
                    user_id=claimed.user_id,
                    organization_id=claimed.organization_id,
                    payload=await self._build_in_progress_payload(
                        latest_summary=latest_summary,
                        meeting_id=claimed.meeting_id,
                        organization_id=claimed.organization_id,
                        job_kind=claimed.job_kind,
                        target_block_sequence=claimed.target_block_sequence,
                    ),
                )

            summary = await self.summary_service.process_job(job=claimed)
            await self._emit_lifecycle_event(
                user_id=claimed.user_id,
                organization_id=claimed.organization_id,
                payload=self._build_summary_payload(summary),
            )
            completed = await self.job_repo.mark_completed(claimed.id)
            if completed is None:
                logger.warning(
                    "Job %s emitted success but could not be marked completed",
                    claimed.id,
                )
        except Exception as exc:  # noqa: BLE001
            failed = await self.job_repo.mark_failed(
                job_id=task.job_id,
                error_message=str(exc),
            )
            if failed is None:
                logger.warning(
                    "Job %s failed but terminal state could not be persisted",
                    task.job_id,
                )
            failed_summary = await self.summary_service.mark_job_failed(
                job=claimed,
                error_message=str(exc),
                latest_summary=latest_summary,
            )
            await self._emit_lifecycle_event(
                user_id=claimed.user_id,
                organization_id=claimed.organization_id,
                payload=self._build_summary_payload(failed_summary),
            )
            raise

    async def _build_in_progress_payload(
        self,
        *,
        latest_summary: MeetingSummary | None,
        meeting_id: str,
        organization_id: str,
        job_kind: MeetingSummaryJobKind,
        target_block_sequence: int,
    ) -> MeetingSummaryPayload:
        """Build the live or finalizing payload while keeping last good bullets visible."""
        language = await self.summary_service.get_summary_language(
            meeting_id=meeting_id,
            organization_id=organization_id,
            latest_summary=latest_summary,
        )
        # Worker emits status="updating"/"finalizing" before generation starts.
        return MeetingSummaryPayload(
            meeting_id=meeting_id,
            status=(
                "finalizing"
                if job_kind == MeetingSummaryJobKind.FINALIZE
                else "updating"
            ),
            bullets=list(latest_summary.bullets) if latest_summary is not None else [],
            is_final=False,
            language=language,
            source_block_sequence=(
                latest_summary.source_block_sequence
                if latest_summary is not None
                else target_block_sequence
            ),
            error_message=None,
        )

    @staticmethod
    def _build_summary_payload(summary: MeetingSummary) -> MeetingSummaryPayload:
        """Convert persisted summary state into socket payload."""
        # Success/failure payloads collapse to status="ready"/"final_ready"/"failed".
        return MeetingSummaryPayload(
            meeting_id=summary.meeting_id,
            status=(
                "final_ready"
                if summary.status == MeetingSummaryStatus.FINAL_READY
                else "failed"
                if summary.status == MeetingSummaryStatus.FAILED
                else "ready"
            ),
            bullets=list(summary.bullets),
            is_final=summary.is_final,
            language=summary.language,
            source_block_sequence=summary.source_block_sequence,
            error_message=summary.error_message,
        )

    async def _emit_lifecycle_event(
        self,
        *,
        user_id: str,
        organization_id: str,
        payload: MeetingSummaryPayload,
    ) -> None:
        """Emit one meeting summary lifecycle event to the user room."""
        await worker_gateway.emit_to_user(
            user_id=user_id,
            event=MeetingRecordEvents.SUMMARY,
            data=payload.model_dump(exclude_none=True, by_alias=True),
            organization_id=organization_id,
        )

    @staticmethod
    def _should_emit_started_event(
        *,
        latest_summary: MeetingSummary | None,
        job_kind: MeetingSummaryJobKind,
        target_block_sequence: int,
    ) -> bool:
        """Skip transient events when the queued job is already superseded."""
        if latest_summary is None:
            return True
        if latest_summary.source_block_sequence < target_block_sequence:
            return True
        if job_kind == MeetingSummaryJobKind.FINALIZE:
            return not latest_summary.is_final
        return latest_summary.status not in {
            MeetingSummaryStatus.READY,
            MeetingSummaryStatus.FINAL_READY,
        }

    async def start(self) -> None:
        """Start the worker processing loop."""
        self.running = True
        logger.info(
            "Meeting summary worker started with max_concurrency=%d",
            self.max_concurrency,
        )

        try:
            while self.running:
                try:
                    await self.run_once()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error in meeting summary worker loop: %s", exc)
                    await asyncio.sleep(1)
        finally:
            await self._wait_for_active_tasks()

        logger.info("Meeting summary worker stopped")

    def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping meeting summary worker...")
        self.running = False


async def setup_connections() -> None:
    """Initialize MongoDB and Redis connections."""
    settings = get_settings()

    await MongoDB.connect(uri=settings.MONGODB_URI, db_name=settings.MONGODB_DB_NAME)
    logger.info("Connected to MongoDB")

    await RedisClient.connect(url=settings.REDIS_URL)
    logger.info("Connected to Redis")


async def cleanup_connections() -> None:
    """Close MongoDB and Redis connections."""
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

    worker = MeetingSummaryWorker()

    def signal_handler(signum, frame) -> None:  # noqa: ARG001
        logger.info("Received signal %s, initiating shutdown...", signum)
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await setup_connections()
        await worker.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Meeting summary worker failed: %s", exc)
        sys.exit(1)
    finally:
        await cleanup_connections()


if __name__ == "__main__":
    asyncio.run(main())
