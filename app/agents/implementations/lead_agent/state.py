"""Lead-agent state schema."""

from langchain.agents import AgentState
from typing_extensions import NotRequired


class LeadAgentState(AgentState):
    """Thread-scoped state for the lead-agent runtime."""

    user_id: str
    organization_id: str | None
    enabled_skill_ids: NotRequired[list[str]]
    active_skill_id: NotRequired[str | None]
    loaded_skills: NotRequired[list[str]]
    allowed_tool_names: NotRequired[list[str]]
    active_skill_version: NotRequired[str | None]
