"""User model and related enums for authentication."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    """System-level user roles."""

    USER = "user"
    SUPER_ADMIN = "super_admin"


class User(BaseModel):
    """User domain model representing a user in the system."""

    id: str = Field(alias="_id")
    email: EmailStr
    hashed_password: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        use_enum_values = True
