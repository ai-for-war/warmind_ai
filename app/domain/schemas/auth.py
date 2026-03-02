"""Authentication schemas for request/response validation."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.domain.models.organization import OrganizationRole
from app.domain.models.user import UserRole


class LoginRequest(BaseModel):
    """Schema for user login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Schema for token response after successful login."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Schema for JWT token payload."""

    sub: str  # user_id
    email: str
    role: str
    exp: int
    iat: int


class UserResponse(BaseModel):
    """Schema for user profile response. Note: hashed_password is NOT included."""

    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    """Schema for creating a new user in the database."""

    email: EmailStr
    hashed_password: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        use_enum_values = True


class CreateUserRequest(BaseModel):
    """Schema for admin/super admin creating a user account."""

    email: EmailStr
    password: str = Field(min_length=8)
    organization_id: Optional[str] = None
    organization_role: OrganizationRole = OrganizationRole.USER

    class Config:
        use_enum_values = True


class BootstrapSuperAdminRequest(BaseModel):
    """Schema for bootstrapping initial super-admin account."""

    email: EmailStr
    password: str = Field(min_length=8)


class CreateUserResponse(BaseModel):
    """Schema for create user response."""

    user: UserResponse
    organization_id: Optional[str] = None
    organization_role: Optional[str] = None
    temporary_password: bool = True


class ChangePasswordRequest(BaseModel):
    """Schema for changing current user's password."""

    current_password: str
    new_password: str = Field(min_length=8)


class ResetPasswordRequest(BaseModel):
    """Schema for admin resetting another user's password."""

    new_password: str = Field(min_length=8)


class UpdateUserRequest(BaseModel):
    """Schema for user update requests (currently only deactivation)."""

    is_active: bool
