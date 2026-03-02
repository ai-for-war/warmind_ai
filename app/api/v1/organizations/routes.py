"""Organization management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_active_user, require_super_admin
from app.common.repo import get_user_repo
from app.common.service import get_org_service
from app.domain.models.user import User
from app.domain.schemas.organization import (
    AddMemberRequest,
    CreateOrganizationRequest,
    OrganizationDetailResponse,
    OrganizationMemberResponse,
    OrganizationResponse,
    UpdateOrganizationRequest,
    UpdateMemberRoleRequest,
)
from app.repo.user_repo import UserRepository
from app.services.organization.organization_service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _to_org_response(organization) -> OrganizationResponse:
    """Map domain Organization to OrganizationResponse."""
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        description=organization.description,
        is_active=organization.is_active,
        created_by=organization.created_by,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: CreateOrganizationRequest,
    current_user: User = Depends(require_super_admin),
    org_service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    """Create organization (Super Admin only)."""
    organization = await org_service.create_organization(
        name=request.name,
        description=request.description,
        created_by=current_user.id,
    )
    return _to_org_response(organization)


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    is_active: Optional[bool] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_super_admin),
    org_service: OrganizationService = Depends(get_org_service),
) -> list[OrganizationResponse]:
    """List organizations (Super Admin only)."""
    organizations = await org_service.list_organizations(
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    return [_to_org_response(org) for org in organizations]


@router.get("/{org_id}", response_model=OrganizationDetailResponse)
async def get_organization(
    org_id: str,
    current_user: User = Depends(require_super_admin),
    org_service: OrganizationService = Depends(get_org_service),
) -> OrganizationDetailResponse:
    """Get organization details (Super Admin only)."""
    organization = await org_service.get_organization(org_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    members = await org_service.get_organization_members(
        organization_id=org_id,
        actor_user=current_user,
    )

    return OrganizationDetailResponse(
        organization=_to_org_response(organization),
        members=members,
        member_count=len(members),
    )


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: str,
    request: UpdateOrganizationRequest,
    _: User = Depends(require_super_admin),
    org_service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    """Update organization details (Super Admin only)."""
    updated = await org_service.update_organization(
        org_id,
        name=request.name,
        description=request.description,
        is_active=request.is_active,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return _to_org_response(updated)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_organization(
    org_id: str,
    _: User = Depends(require_super_admin),
    org_service: OrganizationService = Depends(get_org_service),
) -> None:
    """Deactivate organization (Super Admin only)."""
    success = await org_service.deactivate_organization(org_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )


@router.post(
    "/{org_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    org_id: str,
    request: AddMemberRequest,
    current_user: User = Depends(get_current_active_user),
    org_service: OrganizationService = Depends(get_org_service),
    user_repo: UserRepository = Depends(get_user_repo),
) -> OrganizationMemberResponse:
    """Add member to organization (Super Admin or Org Admin)."""
    member = await org_service.add_member(
        organization_id=org_id,
        user_email=request.user_email,
        role=request.role,
        actor_user=current_user,
    )
    user = await user_repo.find_by_id(member.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return OrganizationMemberResponse(
        user_id=member.user_id,
        email=user.email,
        role=member.role,
        joined_at=member.created_at,
    )


@router.get("/{org_id}/members", response_model=list[OrganizationMemberResponse])
async def list_members(
    org_id: str,
    current_user: User = Depends(get_current_active_user),
    org_service: OrganizationService = Depends(get_org_service),
) -> list[OrganizationMemberResponse]:
    """List organization members (any member can view)."""
    return await org_service.get_organization_members(
        organization_id=org_id,
        actor_user=current_user,
    )


@router.patch("/{org_id}/members/{user_id}", response_model=OrganizationMemberResponse)
async def change_member_role(
    org_id: str,
    user_id: str,
    request: UpdateMemberRoleRequest,
    current_user: User = Depends(get_current_active_user),
    org_service: OrganizationService = Depends(get_org_service),
    user_repo: UserRepository = Depends(get_user_repo),
) -> OrganizationMemberResponse:
    """Change role of a member in organization (Super Admin or Org Admin)."""
    member = await org_service.change_member_role(
        organization_id=org_id,
        user_id=user_id,
        role=request.role,
        actor_user=current_user,
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )
    user = await user_repo.find_by_id(member.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return OrganizationMemberResponse(
        user_id=member.user_id,
        email=user.email,
        role=member.role,
        joined_at=member.created_at,
    )


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: str,
    user_id: str,
    current_user: User = Depends(get_current_active_user),
    org_service: OrganizationService = Depends(get_org_service),
) -> None:
    """Remove member from organization (Super Admin or Org Admin)."""
    removed = await org_service.remove_member(
        organization_id=org_id,
        user_id=user_id,
        actor_user=current_user,
    )
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )
