"""Schemas for lead-agent thread and conversation API payloads."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.conversation import ConversationStatus
from app.domain.models.message import Attachment, MessageMetadata, MessageRole


class LeadAgentSchema(BaseModel):
    """Base schema defaults for lead-agent API payloads."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateLeadAgentThreadRequest(LeadAgentSchema):
    """Schema for creating a new lead-agent thread."""


class CreateLeadAgentThreadResponse(LeadAgentSchema):
    """Schema returned after creating a new lead-agent thread."""

    thread_id: str


class LeadAgentThreadRunRequest(LeadAgentSchema):
    """Schema for submitting a new user turn to a thread."""

    content: str = Field(..., min_length=1, max_length=10000)


class LeadAgentThreadRunResponse(LeadAgentSchema):
    """Schema returned after a lead-agent thread run completes."""

    thread_id: str
    response: str


class LeadAgentSendMessageRequest(LeadAgentSchema):
    """Schema for sending a lead-agent message using a conversation handle."""

    conversation_id: Optional[str] = None
    content: str = Field(..., min_length=1, max_length=10000)


class LeadAgentSendMessageResponse(LeadAgentSchema):
    """Schema returned after accepting a lead-agent message."""

    user_message_id: str
    conversation_id: str


class LeadAgentConversationResponse(LeadAgentSchema):
    """Response schema for a lead-agent conversation summary."""

    id: str
    title: str
    status: ConversationStatus
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    thread_id: Optional[str] = None


class LeadAgentConversationListResponse(LeadAgentSchema):
    """Response schema for a paginated lead-agent conversation list."""

    items: list[LeadAgentConversationResponse]
    total: int
    skip: int
    limit: int


class LeadAgentMessageResponse(LeadAgentSchema):
    """Response schema for a persisted lead-agent message."""

    id: str
    role: MessageRole
    content: str
    attachments: list[Attachment]
    metadata: Optional[MessageMetadata] = None
    is_complete: bool
    created_at: datetime
    thread_id: Optional[str] = None


class LeadAgentMessageListResponse(LeadAgentSchema):
    """Response schema for lead-agent conversation message history."""

    conversation_id: str
    messages: list[LeadAgentMessageResponse]
