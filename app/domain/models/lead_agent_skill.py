"""Domain model for persisted user-created lead-agent skills."""

from datetime import datetime

from pydantic import BaseModel, Field


class LeadAgentSkill(BaseModel):
    """Lead-agent skill definition stored in MongoDB."""

    id: str = Field(alias="_id")
    skill_id: str
    name: str
    description: str
    activation_prompt: str
    allowed_tool_names: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    created_by: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
