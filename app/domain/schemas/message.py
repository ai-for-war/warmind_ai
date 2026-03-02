"""Message schemas for request/response validation."""

from typing import Optional

from pydantic import BaseModel

from app.domain.models.message import (
    Attachment,
    MessageMetadata,
    MessageRole,
)


class MessageCreate(BaseModel):
    """Schema for creating a new message."""

    conversation_id: str
    role: MessageRole
    content: str
    attachments: Optional[list[Attachment]] = None
    metadata: Optional[MessageMetadata] = None
    is_complete: bool = True

    class Config:
        use_enum_values = True


class MessageUpdate(BaseModel):
    """Schema for updating an existing message."""

    content: Optional[str] = None
    is_complete: Optional[bool] = None
    metadata: Optional[MessageMetadata] = None
