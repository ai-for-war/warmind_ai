"""Lead-agent state schema."""

from typing import Any

from langchain.agents import AgentState
from typing_extensions import NotRequired


class LeadAgentState(AgentState):
    """Thread-scoped state for the lead-agent runtime."""

    user_id: str
    organization_id: str | None
    runtime_provider: NotRequired[str | None]
    runtime_model: NotRequired[str | None]
    runtime_reasoning: NotRequired[str | None]
    subagent_enabled: NotRequired[bool]
    orchestration_mode: NotRequired[str | None]
    delegation_depth: NotRequired[int]
    delegation_parent_run_id: NotRequired[str | None]
    delegated_execution_metadata: NotRequired[dict[str, Any] | None]
    enabled_skill_ids: NotRequired[list[str]]
    active_skill_id: NotRequired[str | None]
    loaded_skills: NotRequired[list[str]]
    allowed_tool_names: NotRequired[list[str]]
    active_skill_version: NotRequired[str | None]
