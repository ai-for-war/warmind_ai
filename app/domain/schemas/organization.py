"""Organization and membership schemas for request/response validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.domain.models.organization import OrganizationRole


class CreateOrganizationRequest(BaseModel):
    """Schema for creating an organization."""

    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None


class UpdateOrganizationRequest(BaseModel):
    """Schema for updating an organization."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OrganizationResponse(BaseModel):
    """Schema for organization response."""

    id: str
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


class AddMemberRequest(BaseModel):
    """Schema for adding an existing user to an organization."""

    user_email: EmailStr
    role: OrganizationRole = OrganizationRole.USER

    class Config:
        use_enum_values = True


class UpdateMemberRoleRequest(BaseModel):
    """Schema for updating member role in an organization."""

    role: OrganizationRole

    class Config:
        use_enum_values = True


class OrganizationMemberResponse(BaseModel):
    """Schema for organization member response."""

    user_id: str
    email: str
    role: OrganizationRole
    joined_at: datetime

    class Config:
        use_enum_values = True


class UserOrganizationResponse(BaseModel):
    """Schema for listing organizations where current user is a member."""

    organization: OrganizationResponse
    role: OrganizationRole

    class Config:
        use_enum_values = True


class OrganizationDetailResponse(BaseModel):
    """Schema for organization details including members."""

    organization: OrganizationResponse
    members: list[OrganizationMemberResponse]
    member_count: int
