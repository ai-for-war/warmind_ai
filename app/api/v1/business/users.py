"""User endpoints for profile management."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_active_user
from app.domain.models.user import User
from app.domain.schemas.auth import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """Get current authenticated user's profile.

    Args:
        current_user: User from get_current_active_user dependency

    Returns:
        UserResponse with user profile information (excludes hashed_password)
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=(
            current_user.role
            if isinstance(current_user.role, str)
            else current_user.role.value
        ),
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
