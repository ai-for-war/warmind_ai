"""Domain model for per-user, per-organization lead-agent skill access records."""

from datetime import datetime

from pydantic import BaseModel, Field


class LeadAgentSkillAccess(BaseModel):
    """Persisted lead-agent skill access for one user in one organization."""

    id: str = Field(alias="_id")
    user_id: str
    organization_id: str
    enabled_skill_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
