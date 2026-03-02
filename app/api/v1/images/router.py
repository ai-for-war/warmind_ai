"""Image upload and management API endpoints."""

from fastapi import APIRouter, Depends, Query, Response, status, UploadFile

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.exceptions import AppException
from app.common.repo import get_member_repo
from app.common.service import get_image_service
from app.common.utils import resolve_user_and_org_role
from app.domain.models.user import User
from app.domain.schemas.image import (
    ImageDetailResponse,
    ImageListResponse,
    ImageUploadResponse,
)
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.services.image.image_service import ImageService

router = APIRouter(prefix="/images", tags=["Images"])


@router.post("/upload", response_model=ImageUploadResponse)
async def upload_images(
    files: list[UploadFile],
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    image_service: ImageService = Depends(get_image_service),
) -> ImageUploadResponse:
    """Upload one or more images (max 10 files) for current organization."""
    if not files:
        raise AppException("At least one file is required")
    if len(files) > 10:
        raise AppException("Maximum 10 files per request")

    return await image_service.upload_images(
        files=files,
        user_id=current_user.id,
        org_id=org_context.organization_id,
    )


@router.get("", response_model=ImageListResponse)
async def list_images(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    image_service: ImageService = Depends(get_image_service),
) -> ImageListResponse:
    """List organization images with pagination."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await image_service.list_images(
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
        skip=skip,
        limit=limit,
    )


@router.get("/{image_id}", response_model=ImageDetailResponse)
async def get_image(
    image_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    image_service: ImageService = Depends(get_image_service),
) -> ImageDetailResponse:
    """Get image details and a signed URL."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await image_service.get_image(
        image_id=image_id,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
    )


@router.delete(
    "/{image_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_image(
    image_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    image_service: ImageService = Depends(get_image_service),
) -> Response:
    """Delete image if actor is owner, org admin, or super admin."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )

    await image_service.delete_image(
        image_id=image_id,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
