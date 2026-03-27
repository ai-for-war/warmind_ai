"""Schemas for lead-agent thread creation and execution."""

from pydantic import BaseModel, ConfigDict, Field


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
