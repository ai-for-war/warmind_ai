"""Conversation schemas for request/response validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.domain.models.conversation import ConversationStatus


class ConversationCreate(BaseModel):
    """Schema for creating a new conversation."""

    user_id: str
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    """Schema for updating an existing conversation."""

    title: Optional[str] = None
    status: Optional[ConversationStatus] = None
    message_count: Optional[int] = None
    last_message_at: Optional[datetime] = None

    class Config:
        use_enum_values = True
