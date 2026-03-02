"""Organization service for organization and membership business logic."""

import re
from typing import Optional

from app.common.exceptions import (
    AlreadyMemberError,
    AppException,
    NotMemberError,
    OrganizationNotFoundError,
    PermissionDeniedError,
    UserNotFoundError,
)
from app.domain.models.organization import (
    Organization,
    OrganizationMember,
    OrganizationRole,
)
from app.domain.models.user import User, UserRole
from app.domain.schemas.organization import (
    OrganizationMemberResponse,
    OrganizationResponse,
    UserOrganizationResponse,
)
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.repo.organization_repo import OrganizationRepository
from app.repo.user_repo import UserRepository


class OrganizationService:
    """Service for organization and membership management."""

    def __init__(
        self,
        organization_repo: OrganizationRepository,
        member_repo: OrganizationMemberRepository,
        user_repo: UserRepository,
    ):
        """Initialize OrganizationService with required repositories."""
        self.organization_repo = organization_repo
        self.member_repo = member_repo
        self.user_repo = user_repo

    async def create_organization(
        self,
        *,
        name: str,
        created_by: str,
        description: Optional[str] = None,
    ) -> Organization:
        """Create organization with auto-generated unique slug."""
        slug = await self._generate_unique_slug(name=name)
        return await self.organization_repo.create(
            name=name,
            slug=slug,
            description=description,
            created_by=created_by,
        )

    async def get_organization(self, organization_id: str) -> Optional[Organization]:
        """Get organization by id."""
        return await self.organization_repo.find_by_id(organization_id)

    async def list_organizations(
        self,
        *,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Organization]:
        """List organizations with pagination and optional active-state filter."""
        return await self.organization_repo.list_all(
            is_active=is_active,
            skip=skip,
            limit=limit,
        )

    async def update_organization(
        self,
        organization_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Organization]:
        """Update organization and regenerate slug when name changes."""
        slug: Optional[str] = None
        if name is not None:
            existing_org = await self.organization_repo.find_by_id(organization_id)
            if existing_org is None:
                return None
            slug = await self._generate_unique_slug(
                name=name,
                exclude_organization_id=organization_id,
            )

        return await self.organization_repo.update(
            organization_id,
            name=name,
            slug=slug,
            description=description,
            is_active=is_active,
        )

    async def deactivate_organization(self, organization_id: str) -> bool:
        """Deactivate organization (soft delete)."""
        return await self.organization_repo.deactivate(organization_id)

    async def add_member(
        self,
        *,
        organization_id: str,
        user_email: str,
        role: OrganizationRole,
        actor_user: User,
    ) -> OrganizationMember:
        """Add an existing user to organization."""
        await self._check_can_manage_members(
            actor_user=actor_user,
            organization_id=organization_id,
        )

        target_user = await self.user_repo.find_by_email(user_email)
        if target_user is None:
            raise UserNotFoundError()

        existing_member = await self.member_repo.find_by_user_and_org(
            user_id=target_user.id,
            organization_id=organization_id,
            is_active=True,
        )
        if existing_member is not None:
            raise AlreadyMemberError()

        return await self.member_repo.create(
            user_id=target_user.id,
            organization_id=organization_id,
            role=role,
            added_by=actor_user.id,
        )

    async def remove_member(
        self,
        *,
        organization_id: str,
        user_id: str,
        actor_user: User,
    ) -> bool:
        """Remove (soft delete) member from organization."""
        await self._check_can_manage_members(
            actor_user=actor_user,
            organization_id=organization_id,
        )

        if user_id == actor_user.id:
            raise AppException("Cannot remove yourself")

        member = await self.member_repo.find_by_user_and_org(
            user_id=user_id,
            organization_id=organization_id,
            is_active=True,
        )
        if member is None:
            raise NotMemberError()

        return await self.member_repo.remove(
            user_id=user_id,
            organization_id=organization_id,
        )

    async def change_member_role(
        self,
        *,
        organization_id: str,
        user_id: str,
        role: OrganizationRole,
        actor_user: User,
    ) -> Optional[OrganizationMember]:
        """Change member role within organization."""
        await self._check_can_manage_members(
            actor_user=actor_user,
            organization_id=organization_id,
        )

        if user_id == actor_user.id and role == OrganizationRole.USER:
            raise AppException("Cannot change your own role")

        member = await self.member_repo.find_by_user_and_org(
            user_id=user_id,
            organization_id=organization_id,
            is_active=True,
        )
        if member is None:
            raise NotMemberError()

        return await self.member_repo.update_role(
            user_id=user_id,
            organization_id=organization_id,
            role=role,
        )

    async def get_organization_members(
        self,
        *,
        organization_id: str,
        actor_user: User,
    ) -> list[OrganizationMemberResponse]:
        """Get members of an organization for authorized requester."""
        await self._check_is_member(
            actor_user=actor_user,
            organization_id=organization_id,
        )

        members = await self.member_repo.list_by_organization(
            organization_id=organization_id,
            is_active=True,
        )

        responses: list[OrganizationMemberResponse] = []
        for member in members:
            user = await self.user_repo.find_by_id(member.user_id)
            if user is None:
                continue
            responses.append(
                OrganizationMemberResponse(
                    user_id=member.user_id,
                    email=user.email,
                    role=member.role,
                    joined_at=member.created_at,
                )
            )

        return responses

    async def get_user_organizations(self, user_id: str) -> list[UserOrganizationResponse]:
        """Get active organizations where the user is an active member."""
        memberships = await self.member_repo.list_by_user(user_id=user_id, is_active=True)

        responses: list[UserOrganizationResponse] = []
        for membership in memberships:
            organization = await self.organization_repo.find_by_id(membership.organization_id)
            if organization is None or not organization.is_active:
                continue
            responses.append(
                UserOrganizationResponse(
                    organization=self._to_organization_response(organization),
                    role=membership.role,
                )
            )

        return responses

    async def _check_can_manage_members(
        self,
        *,
        actor_user: User,
        organization_id: str,
    ) -> None:
        """Check whether actor can add/remove/change members in the organization."""
        organization = await self.organization_repo.find_by_id(organization_id)
        if organization is None or not organization.is_active:
            raise OrganizationNotFoundError()

        if self._is_super_admin(actor_user):
            return

        member = await self.member_repo.find_by_user_and_org(
            user_id=actor_user.id,
            organization_id=organization_id,
            is_active=True,
        )
        if member is None:
            raise PermissionDeniedError()

        member_role = member.role if isinstance(member.role, str) else member.role.value
        if member_role != OrganizationRole.ADMIN.value:
            raise PermissionDeniedError()

    async def _check_is_member(
        self,
        *,
        actor_user: User,
        organization_id: str,
    ) -> None:
        """Check whether actor is a member of the organization."""
        organization = await self.organization_repo.find_by_id(organization_id)
        if organization is None or not organization.is_active:
            raise OrganizationNotFoundError()

        if self._is_super_admin(actor_user):
            return

        member = await self.member_repo.find_by_user_and_org(
            user_id=actor_user.id,
            organization_id=organization_id,
            is_active=True,
        )
        if member is None:
            raise PermissionDeniedError()

    async def _generate_unique_slug(
        self,
        *,
        name: str,
        exclude_organization_id: Optional[str] = None,
    ) -> str:
        """Generate unique organization slug from name."""
        base_slug = self._slugify(name)
        slug = base_slug
        suffix = 2

        while True:
            existing = await self.organization_repo.find_by_slug(slug)
            if existing is None:
                return slug
            if exclude_organization_id is not None and existing.id == exclude_organization_id:
                return slug
            slug = f"{base_slug}-{suffix}"
            suffix += 1

    def _slugify(self, name: str) -> str:
        """Convert organization name to kebab-case slug."""
        slug = name.strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")
        return slug or "organization"

    def _is_super_admin(self, user: User) -> bool:
        """Check if user has SUPER_ADMIN system role."""
        user_role = user.role if isinstance(user.role, str) else user.role.value
        return user_role == UserRole.SUPER_ADMIN.value

    def _to_organization_response(self, organization: Organization) -> OrganizationResponse:
        """Convert domain Organization to schema response model."""
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
