"""Conversation model and related enums for AI chat storage."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ConversationStatus(str, Enum):
    """Status of a conversation."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class Conversation(BaseModel):
    """Conversation domain model representing a chat session between user and AI."""

    id: str = Field(alias="_id")
    user_id: str
    organization_id: Optional[str] = None
    title: str
    status: ConversationStatus = ConversationStatus.ACTIVE
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        use_enum_values = True
