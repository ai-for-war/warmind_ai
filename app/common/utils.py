"""Shared utility helpers for role resolution and access checks."""

from app.domain.models.organization import OrganizationRole
from app.domain.models.user import User, UserRole
from app.repo.organization_member_repo import OrganizationMemberRepository


def is_super_admin(user_role: UserRole | str) -> bool:
    """Check if system-level role is SUPER_ADMIN."""
    role = user_role if isinstance(user_role, str) else user_role.value
    return role == UserRole.SUPER_ADMIN.value


def is_org_admin(org_role: OrganizationRole | str | None) -> bool:
    """Check if organization-level role is ADMIN."""
    if org_role is None:
        return False
    role = org_role if isinstance(org_role, str) else org_role.value
    return role == OrganizationRole.ADMIN.value


async def resolve_user_and_org_role(
    current_user: User,
    organization_id: str,
    member_repo: OrganizationMemberRepository,
) -> tuple[str, str | None]:
    """Resolve current user's system role and organization role."""
    user_role = (
        current_user.role
        if isinstance(current_user.role, str)
        else current_user.role.value
    )
    if is_super_admin(user_role):
        return user_role, None

    membership = await member_repo.find_by_user_and_org(
        user_id=current_user.id,
        organization_id=organization_id,
        is_active=True,
    )
    org_role = membership.role if membership is not None else None
    return user_role, org_role
