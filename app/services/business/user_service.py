"""User service for user-related business operations."""

from typing import Optional

from app.domain.models.user import User
from app.repo.user_repo import UserRepository


class UserService:
    """Service for handling user-related operations."""

    def __init__(self, user_repo: UserRepository):
        """Initialize UserService with user repository.

        Args:
            user_repo: UserRepository instance for database operations
        """
        self.user_repo = user_repo

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID.

        Args:
            user_id: User ID to search for

        Returns:
            User instance if found, None otherwise
        """
        return await self.user_repo.find_by_id(user_id)
