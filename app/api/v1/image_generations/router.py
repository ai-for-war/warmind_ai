"""Text-to-image generation job API endpoints."""

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.repo import get_member_repo
from app.common.service import get_image_generation_service
from app.common.utils import resolve_user_and_org_role
from app.domain.models.user import User
from app.domain.schemas.image_generation import (
    CancelImageGenerationJobResponse,
    CreateTextToImageJobRequest,
    CreateTextToImageJobResponse,
    ImageGenerationHistoryResponse,
    ImageGenerationJobDetailResponse,
)
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.services.image.image_generation_service import ImageGenerationService

router = APIRouter(prefix="/image-generations", tags=["Image Generations"])


@router.post(
    "/text-to-image",
    response_model=CreateTextToImageJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_text_to_image_job(
    request: CreateTextToImageJobRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    image_generation_service: ImageGenerationService = Depends(get_image_generation_service),
) -> CreateTextToImageJobResponse:
    """Create a text-to-image generation job and enqueue it for async processing."""
    return await image_generation_service.create_text_to_image_job(
        request=request,
        user_id=current_user.id,
        organization_id=org_context.organization_id,
    )


@router.get("/{job_id}", response_model=ImageGenerationJobDetailResponse)
async def get_image_generation_job_detail(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    image_generation_service: ImageGenerationService = Depends(get_image_generation_service),
) -> ImageGenerationJobDetailResponse:
    """Get one generation job detail with role-aware access checks."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await image_generation_service.get_job_detail(
        job_id=job_id,
        user_id=current_user.id,
        user_role=user_role,
        organization_id=org_context.organization_id,
        org_role=org_role,
    )


@router.get("", response_model=ImageGenerationHistoryResponse)
async def list_image_generation_jobs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    image_generation_service: ImageGenerationService = Depends(get_image_generation_service),
) -> ImageGenerationHistoryResponse:
    """List generation job history scoped by organization and caller role."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await image_generation_service.list_history(
        user_id=current_user.id,
        user_role=user_role,
        organization_id=org_context.organization_id,
        org_role=org_role,
        skip=skip,
        limit=limit,
    )


@router.post("/{job_id}/cancel", response_model=CancelImageGenerationJobResponse)
async def cancel_image_generation_job(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    image_generation_service: ImageGenerationService = Depends(get_image_generation_service),
) -> CancelImageGenerationJobResponse:
    """Cancel a pending generation job if caller has sufficient permission."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await image_generation_service.cancel_job(
        job_id=job_id,
        user_id=current_user.id,
        user_role=user_role,
        organization_id=org_context.organization_id,
        org_role=org_role,
    )

