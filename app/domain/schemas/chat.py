"""Chat schemas for request/response validation and socket payloads."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.models.conversation import ConversationStatus
from app.domain.models.message import Attachment, MessageMetadata, MessageRole


class SendMessageRequest(BaseModel):
    """Schema for sending a chat message."""

    conversation_id: Optional[str] = None
    content: str = Field(..., min_length=1, max_length=10000)


class SendMessageResponse(BaseModel):
    """Schema for send message response."""

    user_message_id: str
    conversation_id: str


# Socket Event Payloads (for documentation and type safety)


class MessageStartedPayload(BaseModel):
    """Payload for chat:message:started event."""

    conversation_id: str


class MessageTokenPayload(BaseModel):
    """Payload for chat:message:token event."""

    conversation_id: str
    token: str


class MessageToolStartPayload(BaseModel):
    """Payload for chat:message:tool_start event."""

    conversation_id: str
    tool_name: str
    tool_call_id: str


class MessageToolEndPayload(BaseModel):
    """Payload for chat:message:tool_end event."""

    conversation_id: str
    tool_call_id: str
    result: str


class MessageCompletedPayload(BaseModel):
    """Payload for chat:message:completed event."""

    conversation_id: str
    message_id: str
    content: str
    metadata: Optional[dict] = None


class MessageFailedPayload(BaseModel):
    """Payload for chat:message:failed event."""

    conversation_id: str
    error: str


# Response Schemas for List/Get Endpoints


class ConversationResponse(BaseModel):
    """Response schema for a single conversation."""

    id: str
    title: str
    status: ConversationStatus
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Response schema for paginated conversation list."""

    items: list[ConversationResponse]
    total: int
    skip: int
    limit: int


class MessageResponse(BaseModel):
    """Response schema for a single message."""

    id: str
    role: MessageRole
    content: str
    attachments: list[Attachment]
    metadata: Optional[MessageMetadata]
    is_complete: bool
    created_at: datetime


class MessageListResponse(BaseModel):
    """Response schema for conversation messages."""

    conversation_id: str
    messages: list[MessageResponse]
