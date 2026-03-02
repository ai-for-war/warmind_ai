"""User management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_active_user
from app.common.exceptions import AppException
from app.common.service import get_org_service, get_user_service
from app.domain.models.user import User
from app.domain.schemas.auth import (
    CreateUserRequest,
    CreateUserResponse,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserResponse,
)
from app.domain.schemas.organization import UserOrganizationResponse
from app.services.organization.organization_service import OrganizationService
from app.services.user.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


def _to_user_response(user: User) -> UserResponse:
    """Map domain User to UserResponse schema."""
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role if isinstance(user.role, str) else user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> CreateUserResponse:
    """Create a new user account (Super Admin or Org Admin scope)."""
    user, membership = await user_service.create_user(
        email=request.email,
        password=request.password,
        actor_user=current_user,
        organization_id=request.organization_id,
        organization_role=request.organization_role,
    )

    return CreateUserResponse(
        user=_to_user_response(user),
        organization_id=membership.organization_id if membership is not None else None,
        organization_role=(
            membership.role if membership is None or isinstance(membership.role, str) else membership.role.value
        )
        if membership is not None
        else None,
        temporary_password=True,
    )


@router.get("", response_model=list[UserResponse])
async def list_users(
    organization_id: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> list[UserResponse]:
    """List users within actor permission scope."""
    users = await user_service.list_users(
        actor_user=current_user,
        organization_id=organization_id,
        skip=skip,
        limit=limit,
    )

    return [_to_user_response(user) for user in users]


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """Get current authenticated user's profile."""
    return _to_user_response(current_user)


@router.get("/me/organizations", response_model=list[UserOrganizationResponse])
async def get_my_organizations(
    current_user: User = Depends(get_current_active_user),
    org_service: OrganizationService = Depends(get_org_service),
) -> list[UserOrganizationResponse]:
    """List organizations of current user."""
    return await org_service.get_user_organizations(current_user.id)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    organization_id: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Get user details within actor scope."""
    user = await user_service.get_user(
        user_id=user_id,
        actor_user=current_user,
        organization_id=organization_id,
    )
    return _to_user_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    organization_id: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Update user account (currently supports deactivation only)."""
    if request.is_active:
        raise AppException("Only deactivation is supported")

    user = await user_service.deactivate_user(
        user_id=user_id,
        actor_user=current_user,
        organization_id=organization_id,
    )
    return _to_user_response(user)


@router.post("/{user_id}/reset-password", response_model=UserResponse)
async def reset_password(
    user_id: str,
    request: ResetPasswordRequest,
    organization_id: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Reset password for a user within actor scope."""
    user = await user_service.reset_password(
        user_id=user_id,
        new_password=request.new_password,
        actor_user=current_user,
        organization_id=organization_id,
    )
    return _to_user_response(user)
