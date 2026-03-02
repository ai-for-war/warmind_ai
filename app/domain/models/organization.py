"""Organization and membership models for multi-tenant architecture."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OrganizationRole(str, Enum):
    """Role of a user within an organization."""

    ADMIN = "admin"
    USER = "user"


class Organization(BaseModel):
    """Organization (Company) entity in the multi-tenant SaaS system."""

    id: str = Field(alias="_id")
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool = True
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        use_enum_values = True


class OrganizationMember(BaseModel):
    """Membership representing the relationship between User and Organization."""

    id: str = Field(alias="_id")
    user_id: str
    organization_id: str
    role: OrganizationRole = OrganizationRole.USER
    added_by: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        use_enum_values = True
