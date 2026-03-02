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
from app.domain.models.user import User, UserRole
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
    _: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    image_service: ImageService = Depends(get_image_service),
) -> ImageListResponse:
    """List organization images with pagination."""
    return await image_service.list_images(
        org_id=org_context.organization_id,
        skip=skip,
        limit=limit,
    )


@router.get("/{image_id}", response_model=ImageDetailResponse)
async def get_image(
    image_id: str,
    _: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    image_service: ImageService = Depends(get_image_service),
) -> ImageDetailResponse:
    """Get image details and a signed URL."""
    return await image_service.get_image(
        image_id=image_id,
        org_id=org_context.organization_id,
    )


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_image(
    image_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    image_service: ImageService = Depends(get_image_service),
) -> Response:
    """Delete image if actor is owner, org admin, or super admin."""
    user_role = current_user.role if isinstance(current_user.role, str) else current_user.role.value

    org_role = None
    if user_role != UserRole.SUPER_ADMIN.value:
        membership = await member_repo.find_by_user_and_org(
            user_id=current_user.id,
            organization_id=org_context.organization_id,
            is_active=True,
        )
        org_role = membership.role if membership is not None else None

    await image_service.delete_image(
        image_id=image_id,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

