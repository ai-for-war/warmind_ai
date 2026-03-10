"""Shared payload builders for image generation socket events."""

from app.domain.schemas.image_generation import (
    ImageGenerationJobStatus,
    ImageGenerationLifecycleEventPayload,
)


def build_image_generation_lifecycle_payload(
    *,
    job_id: str,
    organization_id: str,
    status: str | ImageGenerationJobStatus,
    requested_count: int = 1,
    success_count: int = 0,
    failed_count: int = 0,
    image_ids: list[str] | None = None,
    error_message: str | None = None,
) -> dict:
    """Return normalized lifecycle payload shared by server and worker emitters."""
    status_value = (
        status
        if isinstance(status, ImageGenerationJobStatus)
        else ImageGenerationJobStatus(status)
    )
    payload = ImageGenerationLifecycleEventPayload(
        job_id=job_id,
        organization_id=organization_id,
        status=status_value,
        requested_count=requested_count,
        success_count=success_count,
        failed_count=failed_count,
        image_ids=image_ids or [],
        error_message=error_message,
    )
    return payload.model_dump()

