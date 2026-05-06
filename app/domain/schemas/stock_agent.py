"""Schemas for stock-agent conversation, skill, and tool API payloads."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.conversation import ConversationStatus
from app.domain.models.message import Attachment, MessageMetadata, MessageRole


class StockAgentSchema(BaseModel):
    """Base schema defaults for stock-agent API payloads."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateStockAgentThreadRequest(StockAgentSchema):
    """Schema for creating a new stock-agent thread."""


class CreateStockAgentThreadResponse(StockAgentSchema):
    """Schema returned after creating a new stock-agent thread."""

    thread_id: str


class StockAgentThreadRunRequest(StockAgentSchema):
    """Schema for submitting a new user turn to a thread."""

    content: str = Field(..., min_length=1, max_length=10000)


class StockAgentThreadRunResponse(StockAgentSchema):
    """Schema returned after a stock-agent thread run completes."""

    thread_id: str
    response: str


class StockAgentSendMessageRequest(StockAgentSchema):
    """Schema for sending a stock-agent message using a conversation handle."""

    conversation_id: Optional[str] = None
    content: str = Field(..., min_length=1, max_length=10000)
    provider: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=200)
    reasoning: Optional[str] = Field(default=None, min_length=1, max_length=50)
    subagent_enabled: bool = False


class StockAgentSendMessageResponse(StockAgentSchema):
    """Schema returned after accepting a stock-agent message."""

    user_message_id: str
    conversation_id: str


class StockAgentToolResponse(StockAgentSchema):
    """Response schema for one user-selectable stock-agent tool."""

    tool_name: str
    display_name: str
    description: str
    category: str


class StockAgentToolListResponse(StockAgentSchema):
    """Response schema for the stock-agent selectable tool catalog."""

    items: list[StockAgentToolResponse]


class StockAgentCatalogModelResponse(StockAgentSchema):
    """Response schema for one stock-agent runtime model option."""

    model: str
    reasoning_options: list[str]
    default_reasoning: Optional[str] = None
    is_default: bool = False


class StockAgentCatalogProviderResponse(StockAgentSchema):
    """Response schema for one stock-agent runtime provider option."""

    provider: str
    display_name: str
    models: list[StockAgentCatalogModelResponse]
    is_default: bool = False


class StockAgentCatalogResponse(StockAgentSchema):
    """Response schema for the configurable stock-agent runtime catalog."""

    default_provider: str
    default_model: str
    default_reasoning: Optional[str] = None
    providers: list[StockAgentCatalogProviderResponse]


class StockAgentSkillFilterStatus(str, Enum):
    """Supported status filters for the stock-agent skill list."""

    ALL = "all"
    ENABLED = "enabled"
    DISABLED = "disabled"


class StockAgentCreateSkillRequest(StockAgentSchema):
    """Schema for creating one stock-agent skill."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    activation_prompt: str = Field(..., min_length=1, max_length=20000)
    allowed_tool_names: list[str] = Field(default_factory=list)


class StockAgentUpdateSkillRequest(StockAgentSchema):
    """Schema for updating one stock-agent skill."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    activation_prompt: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=20000,
    )
    allowed_tool_names: Optional[list[str]] = None


class StockAgentSkillResponse(StockAgentSchema):
    """Response schema for one stock-agent skill."""

    skill_id: str
    name: str
    description: str
    activation_prompt: str
    allowed_tool_names: list[str]
    version: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class StockAgentSkillListResponse(StockAgentSchema):
    """Response schema for a paginated stock-agent skill list."""

    items: list[StockAgentSkillResponse]
    total: int
    skip: int
    limit: int


class StockAgentSkillEnablementResponse(StockAgentSchema):
    """Response schema for one skill enablement toggle result."""

    skill_id: str
    is_enabled: bool


class StockAgentConversationResponse(StockAgentSchema):
    """Response schema for a stock-agent conversation summary."""

    id: str
    title: str
    status: ConversationStatus
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    thread_id: Optional[str] = None


class StockAgentConversationListResponse(StockAgentSchema):
    """Response schema for a paginated stock-agent conversation list."""

    items: list[StockAgentConversationResponse]
    total: int
    skip: int
    limit: int


class StockAgentMessageResponse(StockAgentSchema):
    """Response schema for a persisted stock-agent message."""

    id: str
    role: MessageRole
    content: str
    attachments: list[Attachment]
    metadata: Optional[MessageMetadata] = None
    is_complete: bool
    created_at: datetime
    thread_id: Optional[str] = None


class StockAgentMessageListResponse(StockAgentSchema):
    """Response schema for stock-agent conversation message history."""

    conversation_id: str
    messages: list[StockAgentMessageResponse]


class StockAgentPlanTodoResponse(StockAgentSchema):
    """Response schema for one persisted stock-agent todo item."""

    content: str
    status: str


class StockAgentPlanSummaryResponse(StockAgentSchema):
    """Response schema for aggregate plan status counts."""

    total: int
    completed: int
    in_progress: int
    pending: int


class StockAgentPlanResponse(StockAgentSchema):
    """Response schema for the latest persisted stock-agent plan snapshot."""

    conversation_id: str
    todos: list[StockAgentPlanTodoResponse]
    summary: StockAgentPlanSummaryResponse
