"""Message model and related types for AI chat storage."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Role of the message sender, compatible with LangChain."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class AttachmentType(str, Enum):
    """Type of attachment in a message."""

    IMAGE = "image"
    FILE = "file"


class Attachment(BaseModel):
    """Attachment metadata for files/images in messages."""

    type: AttachmentType
    url: str
    filename: str
    mime_type: str
    size_bytes: int

    class Config:
        use_enum_values = True


class TokenUsage(BaseModel):
    """Token usage statistics for AI responses."""

    prompt: int = 0
    completion: int = 0
    total: int = 0


class ToolCall(BaseModel):
    """Tool call information for assistant messages that invoke tools."""

    id: str
    name: str
    arguments: dict


class MessageMetadata(BaseModel):
    """Metadata for AI-generated messages."""

    model: Optional[str] = None
    tokens: Optional[TokenUsage] = None
    latency_ms: Optional[int] = None
    finish_reason: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None


class Message(BaseModel):
    """Message domain model representing a single message in a conversation."""

    id: str = Field(alias="_id")
    conversation_id: str
    role: MessageRole
    content: str
    attachments: list[Attachment] = Field(default_factory=list)
    metadata: Optional[MessageMetadata] = None
    is_complete: bool = True
    created_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        use_enum_values = True
