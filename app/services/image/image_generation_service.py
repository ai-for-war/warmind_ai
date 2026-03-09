"""Service layer for text-to-image generation jobs."""

from __future__ import annotations

from datetime import datetime, timezone

from app.common.event_socket import TextToImageGenerationEvents
from app.common.exceptions import (
    AppException,
    ImageGenerationCancellationConflictError,
    ImageGenerationJobNotFoundError,
    InvalidImageGenerationJobStateError,
    PermissionDeniedError,
)
from app.common.utils import is_org_admin, is_super_admin
from app.config.settings import get_settings
from app.domain.models.image_generation_job import (
    ImageGenerationJob,
    ImageGenerationJobStatus as JobStatusModel,
)
from app.domain.models.organization import OrganizationRole
from app.domain.models.user import UserRole
from app.domain.schemas.image_generation import (
    CancelImageGenerationJobResponse,
    CreateTextToImageJobRequest,
    CreateTextToImageJobResponse,
    ImageGenerationHistoryResponse,
    ImageGenerationJobDetailResponse,
    ImageGenerationJobStatus,
    ImageGenerationJobSummaryItem,
    ImageGenerationLifecycleEventPayload,
    TextToImageGenerationJobRecord,
)
from app.infrastructure.redis.redis_queue import RedisQueue
from app.repo.image_generation_job_repo import ImageGenerationJobRepository
from app.socket_gateway import gateway


class ImageGenerationService:
    """Orchestrates text-to-image job lifecycle for API endpoints."""

    def __init__(
        self,
        image_generation_job_repo: ImageGenerationJobRepository,
        redis_queue: RedisQueue,
    ) -> None:
        self.image_generation_job_repo = image_generation_job_repo
        self.redis_queue = redis_queue
        self.settings = get_settings()

    async def create_text_to_image_job(
        self,
        *,
        request: CreateTextToImageJobRequest,
        user_id: str,
        organization_id: str,
    ) -> CreateTextToImageJobResponse:
        """Create a pending generation job and enqueue async processing."""
        job = await self.image_generation_job_repo.create(
            {
                "organization_id": organization_id,
                "created_by": user_id,
                "type": "text_to_image",
                "provider": "minimax",
                "provider_model": "image-01",
                "status": JobStatusModel.PENDING.value,
                "prompt": request.prompt,
                "aspect_ratio": request.aspect_ratio.value,
                "seed": request.seed,
                "prompt_optimizer": request.prompt_optimizer,
                "requested_count": 1,
                "retry_count": 0,
                "requested_at": datetime.now(timezone.utc),
            }
        )

        enqueued = await self.redis_queue.enqueue(
            queue_name=self.settings.IMAGE_GENERATION_QUEUE_NAME,
            data={
                "job_id": job.id,
                "organization_id": organization_id,
                "user_id": user_id,
                "retry_count": 0,
            },
        )
        if not enqueued:
            raise AppException("Failed to enqueue image generation job")

        await self._emit_created_event(job=job)
        return CreateTextToImageJobResponse(
            job_id=job.id,
            status=ImageGenerationJobStatus(job.status),
        )

    async def list_history(
        self,
        *,
        user_id: str,
        user_role: UserRole | str,
        organization_id: str,
        org_role: OrganizationRole | str | None,
        skip: int = 0,
        limit: int = 20,
    ) -> ImageGenerationHistoryResponse:
        """List generation jobs with role-aware visibility."""
        if is_super_admin(user_role) or is_org_admin(org_role):
            result = await self.image_generation_job_repo.list_by_organization(
                organization_id=organization_id,
                skip=skip,
                limit=limit,
            )
        else:
            result = await self.image_generation_job_repo.list_by_creator_and_organization(
                organization_id=organization_id,
                created_by=user_id,
                skip=skip,
                limit=limit,
            )

        return ImageGenerationHistoryResponse(
            items=[self._to_summary_item(job) for job in result.items],
            total=result.total,
            skip=skip,
            limit=limit,
        )

    async def get_job_detail(
        self,
        *,
        job_id: str,
        user_id: str,
        user_role: UserRole | str,
        organization_id: str,
        org_role: OrganizationRole | str | None,
    ) -> ImageGenerationJobDetailResponse:
        """Get generation job detail with role-aware permission checks."""
        job = await self.image_generation_job_repo.find_by_id_and_org(
            job_id=job_id,
            organization_id=organization_id,
        )
        if job is None:
            raise ImageGenerationJobNotFoundError()

        if not self._can_access_job(
            job=job,
            user_id=user_id,
            user_role=user_role,
            org_role=org_role,
        ):
            raise PermissionDeniedError()

        return ImageGenerationJobDetailResponse(job=self._to_job_record(job))

    async def cancel_job(
        self,
        *,
        job_id: str,
        user_id: str,
        user_role: UserRole | str,
        organization_id: str,
        org_role: OrganizationRole | str | None,
    ) -> CancelImageGenerationJobResponse:
        """Cancel a pending job using atomic compare-and-set semantics."""
        existing = await self.image_generation_job_repo.find_by_id_and_org(
            job_id=job_id,
            organization_id=organization_id,
        )
        if existing is None:
            raise ImageGenerationJobNotFoundError()

        if not self._can_access_job(
            job=existing,
            user_id=user_id,
            user_role=user_role,
            org_role=org_role,
        ):
            raise PermissionDeniedError()

        actor_scope = {"organization_id": organization_id}
        if not (is_super_admin(user_role) or is_org_admin(org_role)):
            actor_scope["created_by"] = user_id

        cancelled = await self.image_generation_job_repo.cancel_pending_job(
            job_id=job_id,
            actor_scope=actor_scope,
        )
        if cancelled is None:
            current = await self.image_generation_job_repo.find_by_id_and_org(
                job_id=job_id,
                organization_id=organization_id,
            )
            if current is None:
                raise ImageGenerationJobNotFoundError()

            if current.status == JobStatusModel.PROCESSING.value:
                raise ImageGenerationCancellationConflictError()

            raise InvalidImageGenerationJobStateError(
                f"Cannot cancel job in '{current.status}' state"
            )

        await self._emit_cancelled_event(job=cancelled)
        return CancelImageGenerationJobResponse(
            job_id=cancelled.id,
            status=ImageGenerationJobStatus(cancelled.status),
            cancelled_at=cancelled.cancelled_at or datetime.now(timezone.utc),
        )

    @staticmethod
    def _can_access_job(
        *,
        job: ImageGenerationJob,
        user_id: str,
        user_role: UserRole | str,
        org_role: OrganizationRole | str | None,
    ) -> bool:
        """Apply 3-tier permission model for generation jobs."""
        if is_super_admin(user_role):
            return True
        if is_org_admin(org_role):
            return True
        return job.created_by == user_id

    def _to_job_record(self, job: ImageGenerationJob) -> TextToImageGenerationJobRecord:
        """Convert domain job model to API detail record."""
        return TextToImageGenerationJobRecord(
            id=job.id,
            organization_id=job.organization_id,
            created_by=job.created_by,
            type=job.type,
            provider=job.provider,
            provider_model=job.provider_model,
            status=ImageGenerationJobStatus(job.status),
            prompt=job.prompt,
            aspect_ratio=job.aspect_ratio,
            seed=job.seed,
            prompt_optimizer=job.prompt_optimizer,
            requested_count=job.requested_count,
            retry_count=job.retry_count,
            provider_trace_id=job.provider_trace_id,
            output_image_ids=job.output_image_ids,
            success_count=job.success_count,
            failed_count=job.failed_count,
            error_code=job.error_code,
            error_message=job.error_message,
            requested_at=job.requested_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            cancelled_at=job.cancelled_at,
        )

    def _to_summary_item(self, job: ImageGenerationJob) -> ImageGenerationJobSummaryItem:
        """Convert domain job model to history summary item."""
        return ImageGenerationJobSummaryItem(
            id=job.id,
            status=ImageGenerationJobStatus(job.status),
            prompt=job.prompt,
            aspect_ratio=job.aspect_ratio,
            requested_at=job.requested_at,
            completed_at=job.completed_at,
            output_image_ids=job.output_image_ids,
            success_count=job.success_count,
            failed_count=job.failed_count,
        )

    async def _emit_created_event(self, job: ImageGenerationJob) -> None:
        """Emit created event after job persistence."""
        payload = ImageGenerationLifecycleEventPayload(
            job_id=job.id,
            organization_id=job.organization_id,
            status=ImageGenerationJobStatus.PENDING,
            requested_count=job.requested_count,
            success_count=job.success_count,
            failed_count=job.failed_count,
            image_ids=job.output_image_ids,
            error_message=job.error_message,
        )
        await gateway.emit_to_user(
            user_id=job.created_by,
            event=TextToImageGenerationEvents.CREATED,
            data=payload.model_dump(),
            organization_id=job.organization_id,
        )

    async def _emit_cancelled_event(self, job: ImageGenerationJob) -> None:
        """Emit cancelled event after cancellation persistence."""
        payload = ImageGenerationLifecycleEventPayload(
            job_id=job.id,
            organization_id=job.organization_id,
            status=ImageGenerationJobStatus.CANCELLED,
            requested_count=job.requested_count,
            success_count=job.success_count,
            failed_count=job.failed_count,
            image_ids=job.output_image_ids,
            error_message=job.error_message,
        )
        await gateway.emit_to_user(
            user_id=job.created_by,
            event=TextToImageGenerationEvents.CANCELLED,
            data=payload.model_dump(),
            organization_id=job.organization_id,
        )
