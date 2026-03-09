"""Image generation worker for processing text-to-image jobs from Redis queue."""

from __future__ import annotations

import asyncio
import base64
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.common.event_socket import TextToImageGenerationEvents
from app.common.image_generation_socket import build_image_generation_lifecycle_payload
from app.common.exceptions import (
    ImageGenerationNonRetryableProviderError,
    ImageGenerationRetryableProviderError,
)
from app.common.repo import get_image_generation_job_repo, get_image_repo
from app.common.service import (
    get_cloudinary_client,
    get_minimax_image_client,
    get_redis_queue,
)
from app.config.settings import get_settings
from app.domain.models.image import ImageSource
from app.domain.models.image_generation_job import ImageGenerationJobStatus
from app.infrastructure.database.mongodb import MongoDB
from app.infrastructure.redis.client import RedisClient
from app.repo.image_generation_job_repo import ImageGenerationJobRepository
from app.repo.image_repo import ImageRepository
from app.socket_gateway.worker_gateway import worker_gateway

logger = logging.getLogger(__name__)


@dataclass
class ImageGenerationTask:
    """Represents one queued image generation task."""

    job_id: str
    organization_id: str
    user_id: str
    queued_at: str
    retry_count: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImageGenerationTask":
        """Create task from queue payload."""
        return cls(
            job_id=data["job_id"],
            organization_id=data["organization_id"],
            user_id=data["user_id"],
            queued_at=data.get("queued_at", datetime.now(timezone.utc).isoformat()),
            retry_count=data.get("retry_count", 0),
        )


class ImageGenerationWorker:
    """Worker consuming queued text-to-image jobs and persisting outputs."""

    DEQUEUE_TIMEOUT = 5

    def __init__(self) -> None:
        self.settings = get_settings()
        self.running = False
        self._queue: Optional[Any] = None
        self._job_repo: Optional[ImageGenerationJobRepository] = None
        self._image_repo: Optional[ImageRepository] = None
        self._cloudinary_client: Optional[Any] = None
        self._minimax_image_client: Optional[Any] = None

    @property
    def queue(self):
        if self._queue is None:
            self._queue = get_redis_queue()
        return self._queue

    @property
    def job_repo(self) -> ImageGenerationJobRepository:
        if self._job_repo is None:
            self._job_repo = get_image_generation_job_repo()
        return self._job_repo

    @property
    def image_repo(self) -> ImageRepository:
        if self._image_repo is None:
            self._image_repo = get_image_repo()
        return self._image_repo

    @property
    def cloudinary_client(self):
        if self._cloudinary_client is None:
            self._cloudinary_client = get_cloudinary_client()
        return self._cloudinary_client

    @property
    def minimax_image_client(self):
        if self._minimax_image_client is None:
            self._minimax_image_client = get_minimax_image_client()
        return self._minimax_image_client

    async def run_once(self) -> bool:
        """Process a single queue item if available."""
        task_data = await self.queue.dequeue(
            queue_name=self.settings.IMAGE_GENERATION_QUEUE_NAME,
            timeout=self.DEQUEUE_TIMEOUT,
        )
        if task_data is None:
            return False

        task = ImageGenerationTask.from_dict(task_data)
        await self.process_task(task)
        return True

    async def process_task(self, task: ImageGenerationTask) -> None:
        """Execute one text-to-image job from queued payload."""
        job = await self.job_repo.find_by_id_and_org(
            job_id=task.job_id,
            organization_id=task.organization_id,
        )
        if job is None:
            logger.info("Skip task %s: job not found", task.job_id)
            return

        if job.status in {
            ImageGenerationJobStatus.CANCELLED.value,
            ImageGenerationJobStatus.SUCCEEDED.value,
            ImageGenerationJobStatus.FAILED.value,
        }:
            logger.info("Skip task %s: job already terminal (%s)", task.job_id, job.status)
            return

        claimed = await self.job_repo.claim_pending_job(task.job_id)
        if claimed is None:
            logger.info("Skip task %s: pending claim lost (already claimed/cancelled)", task.job_id)
            return

        await self._emit_processing_event(task=task, status=claimed.status)

        try:
            provider_result = await self.minimax_image_client.generate_text_to_image(
                prompt=claimed.prompt,
                aspect_ratio=claimed.aspect_ratio,
                seed=claimed.seed,
                prompt_optimizer=claimed.prompt_optimizer,
            )

            image_bytes = self._decode_base64_image(provider_result.images_base64[0])
            timestamp_folder = datetime.now(timezone.utc).strftime("%Y-%m")
            unique_folder = f"{timestamp_folder}/{uuid4().hex}"
            upload_result = await self.cloudinary_client.upload(
                file_bytes=image_bytes,
                filename="generated-image.jpg",
                folder=unique_folder,
                org_id=claimed.organization_id,
            )

            public_id = upload_result.get("public_id")
            if not public_id:
                raise RuntimeError("Missing public_id from Cloudinary upload result")

            created_image = await self.image_repo.create(
                {
                    "public_id": public_id,
                    "organization_id": claimed.organization_id,
                    "uploaded_by": claimed.created_by,
                    "original_filename": "generated-image.jpg",
                    "mime_type": "image/jpeg",
                    "size_bytes": len(image_bytes),
                    "cloudinary_folder": f"{claimed.organization_id}/{unique_folder}",
                    "source": ImageSource.GENERATION.value,
                    "generation_job_id": claimed.id,
                    "provider": claimed.provider,
                    "provider_model": claimed.provider_model,
                }
            )

            succeeded = await self.job_repo.mark_succeeded(
                job_id=claimed.id,
                provider_trace_id=provider_result.provider_trace_id,
                output_image_ids=[created_image.id],
                success_count=max(1, provider_result.success_count),
                failed_count=provider_result.failed_count,
            )
            if succeeded is None:
                logger.warning("Job %s was not updated to succeeded", claimed.id)
                return

            await self._emit_succeeded_event(
                task=task,
                status=succeeded.status,
                image_ids=succeeded.output_image_ids,
                success_count=succeeded.success_count,
                failed_count=succeeded.failed_count,
            )
        except ImageGenerationNonRetryableProviderError as exc:
            await self._mark_failed_and_emit(
                task=task,
                job_id=claimed.id,
                error_code="provider_non_retryable",
                error_message=exc.message,
            )
        except ImageGenerationRetryableProviderError as exc:
            await self._mark_failed_and_emit(
                task=task,
                job_id=claimed.id,
                error_code="provider_retryable",
                error_message=exc.message,
            )
        except Exception as exc:  # noqa: BLE001
            await self._mark_failed_and_emit(
                task=task,
                job_id=claimed.id,
                error_code="storage_or_processing_error",
                error_message=str(exc),
            )

    async def _mark_failed_and_emit(
        self,
        *,
        task: ImageGenerationTask,
        job_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        """Persist failed terminal state and emit failed event."""
        failed = await self.job_repo.mark_failed(
            job_id=job_id,
            error_code=error_code,
            error_message=error_message,
        )
        if failed is None:
            logger.warning("Job %s was not updated to failed", job_id)
            return

        await worker_gateway.emit_to_user(
            user_id=task.user_id,
            event=TextToImageGenerationEvents.FAILED,
            data=build_image_generation_lifecycle_payload(
                job_id=job_id,
                organization_id=task.organization_id,
                status=failed.status,
                requested_count=failed.requested_count,
                success_count=failed.success_count,
                failed_count=failed.failed_count,
                image_ids=failed.output_image_ids,
                error_message=failed.error_message,
            ),
            organization_id=task.organization_id,
        )

    async def _emit_processing_event(self, *, task: ImageGenerationTask, status: str) -> None:
        """Emit processing event after processing state is persisted."""
        await worker_gateway.emit_to_user(
            user_id=task.user_id,
            event=TextToImageGenerationEvents.PROCESSING,
            data=build_image_generation_lifecycle_payload(
                job_id=task.job_id,
                organization_id=task.organization_id,
                status=status,
                requested_count=1,
                success_count=0,
                failed_count=0,
                image_ids=[],
            ),
            organization_id=task.organization_id,
        )

    async def _emit_succeeded_event(
        self,
        *,
        task: ImageGenerationTask,
        status: str,
        image_ids: list[str],
        success_count: int,
        failed_count: int,
    ) -> None:
        """Emit succeeded event after success state is persisted."""
        await worker_gateway.emit_to_user(
            user_id=task.user_id,
            event=TextToImageGenerationEvents.SUCCEEDED,
            data=build_image_generation_lifecycle_payload(
                job_id=task.job_id,
                organization_id=task.organization_id,
                status=status,
                requested_count=1,
                success_count=success_count,
                failed_count=failed_count,
                image_ids=image_ids,
            ),
            organization_id=task.organization_id,
        )

    @staticmethod
    def _decode_base64_image(value: str) -> bytes:
        """Decode provider image base64 (supports plain and data URL)."""
        normalized = value.strip()
        if "," in normalized and normalized.lower().startswith("data:"):
            normalized = normalized.split(",", 1)[1]
        return base64.b64decode(normalized)

    async def start(self) -> None:
        """Start the worker processing loop."""
        self.running = True
        logger.info("Image generation worker started")

        while self.running:
            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error in image generation worker loop: %s", exc)
                await asyncio.sleep(1)

        logger.info("Image generation worker stopped")

    def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping image generation worker...")
        self.running = False


async def setup_connections() -> None:
    """Initialize MongoDB and Redis connections."""
    settings = get_settings()

    await MongoDB.connect(uri=settings.MONGODB_URI, db_name=settings.MONGODB_DB_NAME)
    logger.info("Connected to MongoDB")

    await RedisClient.connect(url=settings.REDIS_URL)
    logger.info("Connected to Redis")


async def cleanup_connections() -> None:
    """Close MongoDB, Redis, and provider client connections."""
    try:
        minimax_image_client = get_minimax_image_client()
        await minimax_image_client.close()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to close MiniMax image client")

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

    worker = ImageGenerationWorker()

    def signal_handler(signum, frame) -> None:  # noqa: ARG001
        logger.info("Received signal %s, initiating shutdown...", signum)
        worker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await setup_connections()
        await worker.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Image generation worker failed: %s", exc)
        sys.exit(1)
    finally:
        await cleanup_connections()


if __name__ == "__main__":
    asyncio.run(main())
