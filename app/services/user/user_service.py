"""User service for admin user management operations."""

from typing import Optional

from app.common.exceptions import (
    AppException,
    EmailAlreadyExistsError,
    OrganizationNotFoundError,
    PermissionDeniedError,
    UserNotFoundError,
)
from app.domain.models.organization import OrganizationMember, OrganizationRole
from app.domain.models.user import User, UserRole
from app.infrastructure.security.password import hash_password
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.repo.organization_repo import OrganizationRepository
from app.repo.user_repo import UserRepository


class UserService:
    """Service for user management operations under role-based permissions."""

    def __init__(
        self,
        user_repo: UserRepository,
        organization_repo: OrganizationRepository,
        member_repo: OrganizationMemberRepository,
    ):
        """Initialize UserService with required repositories."""
        self.user_repo = user_repo
        self.organization_repo = organization_repo
        self.member_repo = member_repo

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        actor_user: User,
        organization_id: Optional[str] = None,
        organization_role: OrganizationRole = OrganizationRole.USER,
    ) -> tuple[User, Optional[OrganizationMember]]:
        """Create user by Super Admin or Org Admin."""
        existing_user = await self.user_repo.find_by_email(email)
        if existing_user is not None:
            raise EmailAlreadyExistsError()

        is_super_admin = self._is_super_admin(actor_user)
        if not is_super_admin:
            if organization_id is None:
                raise AppException("Organization ID required")
            await self._ensure_org_admin(
                actor_user_id=actor_user.id,
                organization_id=organization_id,
            )

        if organization_id is not None:
            organization = await self.organization_repo.find_by_id(organization_id)
            if organization is None or not organization.is_active:
                raise OrganizationNotFoundError()

        new_user = await self.user_repo.create(
            email=email,
            hashed_password=hash_password(password),
        )

        membership: Optional[OrganizationMember] = None
        if organization_id is not None:
            membership = await self.member_repo.create(
                user_id=new_user.id,
                organization_id=organization_id,
                role=organization_role,
                added_by=actor_user.id,
            )

        return new_user, membership

    async def list_users(
        self,
        *,
        actor_user: User,
        organization_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        """List users by permission scope."""
        if self._is_super_admin(actor_user):
            if organization_id is None:
                return await self.user_repo.list_all(skip=skip, limit=limit)
            return await self._list_users_by_organization(
                organization_id=organization_id,
                skip=skip,
                limit=limit,
            )

        if organization_id is None:
            raise AppException("Organization ID required")

        await self._ensure_org_admin(
            actor_user_id=actor_user.id,
            organization_id=organization_id,
        )
        return await self._list_users_by_organization(
            organization_id=organization_id,
            skip=skip,
            limit=limit,
        )

    async def get_user(
        self,
        *,
        user_id: str,
        actor_user: User,
        organization_id: Optional[str] = None,
    ) -> User:
        """Get user details within actor permission scope."""
        user = await self.user_repo.find_by_id(user_id)
        if user is None:
            raise UserNotFoundError()

        if self._is_super_admin(actor_user):
            return user

        if organization_id is None:
            raise AppException("Organization ID required")

        await self._ensure_org_admin(
            actor_user_id=actor_user.id,
            organization_id=organization_id,
        )

        is_target_member = await self.member_repo.find_by_user_and_org(
            user_id=user_id,
            organization_id=organization_id,
            is_active=True,
        )
        if is_target_member is None:
            raise PermissionDeniedError()

        return user

    async def deactivate_user(
        self,
        *,
        user_id: str,
        actor_user: User,
        organization_id: Optional[str] = None,
    ) -> User:
        """Deactivate a user account in actor permission scope."""
        if user_id == actor_user.id:
            raise AppException("Cannot deactivate yourself")

        await self._check_can_manage_target_user(
            actor_user=actor_user,
            target_user_id=user_id,
            organization_id=organization_id,
        )

        updated_user = await self.user_repo.update_is_active(user_id, is_active=False)
        if updated_user is None:
            raise UserNotFoundError()
        return updated_user

    async def reset_password(
        self,
        *,
        user_id: str,
        new_password: str,
        actor_user: User,
        organization_id: Optional[str] = None,
    ) -> User:
        """Reset user password in actor permission scope."""
        await self._check_can_manage_target_user(
            actor_user=actor_user,
            target_user_id=user_id,
            organization_id=organization_id,
        )

        updated_user = await self.user_repo.update_password(
            user_id=user_id,
            hashed_password=hash_password(new_password),
        )
        if updated_user is None:
            raise UserNotFoundError()
        return updated_user

    async def _check_can_manage_target_user(
        self,
        *,
        actor_user: User,
        target_user_id: str,
        organization_id: Optional[str] = None,
    ) -> None:
        """Check whether actor can manage the target user."""
        target_user = await self.user_repo.find_by_id(target_user_id)
        if target_user is None:
            raise UserNotFoundError()

        if self._is_super_admin(actor_user):
            return

        if organization_id is None:
            raise AppException("Organization ID required")

        await self._ensure_org_admin(
            actor_user_id=actor_user.id,
            organization_id=organization_id,
        )

        is_target_member = await self.member_repo.find_by_user_and_org(
            user_id=target_user_id,
            organization_id=organization_id,
            is_active=True,
        )
        if is_target_member is None:
            raise PermissionDeniedError()

    async def _ensure_org_admin(self, *, actor_user_id: str, organization_id: str) -> None:
        """Ensure the actor is active ADMIN member of organization."""
        organization = await self.organization_repo.find_by_id(organization_id)
        if organization is None or not organization.is_active:
            raise OrganizationNotFoundError()

        member = await self.member_repo.find_by_user_and_org(
            user_id=actor_user_id,
            organization_id=organization_id,
            is_active=True,
        )
        if member is None:
            raise PermissionDeniedError()

        member_role = member.role if isinstance(member.role, str) else member.role.value
        if member_role != OrganizationRole.ADMIN.value:
            raise PermissionDeniedError()

    async def _list_users_by_organization(
        self,
        *,
        organization_id: str,
        skip: int,
        limit: int,
    ) -> list[User]:
        """List users that are active members of a specific organization."""
        members = await self.member_repo.list_by_organization(
            organization_id=organization_id,
            is_active=True,
        )

        users: list[User] = []
        for member in members[skip : skip + limit]:
            user = await self.user_repo.find_by_id(member.user_id)
            if user is not None:
                users.append(user)
        return users

    def _is_super_admin(self, user: User) -> bool:
        """Check if user has SUPER_ADMIN system role."""
        user_role = user.role if isinstance(user.role, str) else user.role.value
        return user_role == UserRole.SUPER_ADMIN.value
