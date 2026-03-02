"""Shared dependencies for API endpoints."""

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.common.exceptions import InvalidTokenError
from app.common.repo import get_member_repo, get_org_repo, get_user_repo
from app.common.service import get_auth_service
from app.domain.models.organization import OrganizationRole
from app.domain.models.user import User, UserRole
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.repo.organization_repo import OrganizationRepository
from app.repo.user_repo import UserRepository
from app.services.auth.auth_service import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@dataclass
class OrganizationContext:
    """Resolved organization context for current request."""

    organization_id: str


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
    user_repo: UserRepository = Depends(get_user_repo),
) -> User:
    """Get current user from JWT token.

    Args:
        token: JWT token from Authorization header
        auth_service: AuthService dependency
        user_repo: UserRepository dependency

    Returns:
        User instance

    Raises:
        HTTPException: 401 if token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = auth_service.verify_token(token)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user = await user_repo.find_by_id(payload.sub)
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user.

    Args:
        current_user: User from get_current_user dependency

    Returns:
        User instance if active

    Raises:
        HTTPException: 401 if user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive",
        )
    return current_user


async def get_current_organization_context(
    x_organization_id: str | None = Header(default=None, alias="X-Organization-ID"),
    current_user: User = Depends(get_current_active_user),
    org_repo: OrganizationRepository = Depends(get_org_repo),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
) -> OrganizationContext:
    """Validate organization header and current user's access to that organization."""
    if not x_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Organization-ID header is required",
        )

    organization = await org_repo.find_by_id(x_organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    user_role = current_user.role if isinstance(current_user.role, str) else current_user.role.value
    if user_role == UserRole.SUPER_ADMIN.value:
        return OrganizationContext(organization_id=x_organization_id)

    membership = await member_repo.find_by_user_and_org(
        user_id=current_user.id,
        organization_id=x_organization_id,
        is_active=True,
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )

    return OrganizationContext(organization_id=x_organization_id)


async def require_org_admin(
    current_user: User = Depends(get_current_active_user),
    context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
) -> User:
    """Require org-admin privileges for current organization context."""
    user_role = current_user.role if isinstance(current_user.role, str) else current_user.role.value
    if user_role == UserRole.SUPER_ADMIN.value:
        return current_user

    membership = await member_repo.find_by_user_and_org(
        user_id=current_user.id,
        organization_id=context.organization_id,
        is_active=True,
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )

    member_role = membership.role if isinstance(membership.role, str) else membership.role.value
    if member_role != OrganizationRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )
    return current_user


async def require_super_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Require super-admin role for endpoint access.

    Args:
        current_user: User from get_current_active_user dependency

    Returns:
        User instance if super-admin

    Raises:
        HTTPException: 403 if user is not super-admin
    """
    user_role = current_user.role
    if isinstance(user_role, str):
        is_super_admin = user_role == UserRole.SUPER_ADMIN.value
    else:
        is_super_admin = user_role == UserRole.SUPER_ADMIN

    if not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )
    return current_user
