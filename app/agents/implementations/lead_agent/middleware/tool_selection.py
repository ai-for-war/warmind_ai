"""Tool selection middleware for the lead-agent runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.tools import BaseTool

from app.agents.implementations.lead_agent.middleware.constants import (
    BASE_SKILL_TOOL_NAMES,
    DELEGATION_TOOL_NAME,
)
from app.agents.implementations.lead_agent.middleware.shared import (
    as_state_dict,
    normalize_bool,
    normalize_non_negative_int,
    normalize_optional_string,
    normalize_unique_strings,
    tool_name,
)
from app.agents.implementations.lead_agent.state import LeadAgentState


class LeadAgentToolSelectionMiddleware(AgentMiddleware[LeadAgentState, None, Any]):
    """Filter visible tools to the base or active-skill subset for each call."""

    state_schema = LeadAgentState
    tools: Sequence[BaseTool] = ()

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler,
    ) -> ModelResponse[Any]:
        state = as_state_dict(request.state)
        active_skill_id = normalize_optional_string(state.get("active_skill_id"))
        allowed_tool_names = normalize_unique_strings(state.get("allowed_tool_names", []))
        subagent_enabled = normalize_bool(state.get("subagent_enabled"))
        delegation_depth = normalize_non_negative_int(state.get("delegation_depth"))

        visible_tool_names = _visible_tool_names(
            active_skill_id=active_skill_id,
            allowed_tool_names=allowed_tool_names,
            subagent_enabled=subagent_enabled,
            delegation_depth=delegation_depth,
        )
        filtered_tools = [
            candidate for candidate in request.tools if tool_name(candidate) in visible_tool_names
        ]
        return await handler(request.override(tools=filtered_tools))


def _visible_tool_names(
    *,
    active_skill_id: str | None,
    allowed_tool_names: Sequence[str],
    subagent_enabled: bool,
    delegation_depth: int,
) -> set[str]:
    """Resolve the visible tool names for the current model call."""
    if not active_skill_id:
        visible_tool_names = set(BASE_SKILL_TOOL_NAMES)
    else:
        visible_tool_names = set(BASE_SKILL_TOOL_NAMES).union(allowed_tool_names)

    if subagent_enabled and delegation_depth == 0:
        visible_tool_names.add(DELEGATION_TOOL_NAME)

    return visible_tool_names
