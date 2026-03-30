"""Schemas for lead-agent conversation, skill, and tool API payloads."""

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


class LeadAgentToolResponse(LeadAgentSchema):
    """Response schema for one user-selectable lead-agent tool."""

    tool_name: str
    display_name: str
    description: str
    category: str


class LeadAgentToolListResponse(LeadAgentSchema):
    """Response schema for the lead-agent selectable tool catalog."""

    items: list[LeadAgentToolResponse]


class LeadAgentCreateSkillRequest(LeadAgentSchema):
    """Schema for creating one lead-agent skill."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    activation_prompt: str = Field(..., min_length=1, max_length=20000)
    allowed_tool_names: list[str] = Field(default_factory=list)


class LeadAgentUpdateSkillRequest(LeadAgentSchema):
    """Schema for updating one lead-agent skill."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    activation_prompt: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=20000,
    )
    allowed_tool_names: Optional[list[str]] = None


class LeadAgentSkillResponse(LeadAgentSchema):
    """Response schema for one lead-agent skill."""

    skill_id: str
    name: str
    description: str
    activation_prompt: str
    allowed_tool_names: list[str]
    version: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class LeadAgentSkillListResponse(LeadAgentSchema):
    """Response schema for a paginated lead-agent skill list."""

    items: list[LeadAgentSkillResponse]
    total: int
    skip: int
    limit: int


class LeadAgentSkillEnablementResponse(LeadAgentSchema):
    """Response schema for one skill enablement toggle result."""

    skill_id: str
    is_enabled: bool


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
