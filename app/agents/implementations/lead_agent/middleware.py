"""Lead-agent middleware for skill-aware prompt injection and tool exposure."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from app.agents.implementations.lead_agent.state import LeadAgentState
from app.services.ai.lead_agent_skill_access_resolver import (
    LeadAgentSkillAccessResolver,
)

_BASE_SKILL_TOOL_NAMES = {"load_skill"}


class LeadAgentSkillPromptMiddleware(AgentMiddleware[LeadAgentState, None, Any]):
    """Inject skill discovery and activation prompts before each model call."""

    state_schema = LeadAgentState
    tools: Sequence[BaseTool] = ()

    def __init__(
        self,
        skill_access_resolver: LeadAgentSkillAccessResolver | None = None,
    ) -> None:
        self.skill_access_resolver = skill_access_resolver

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler,
    ) -> ModelResponse[Any]:
        state = _as_state_dict(request.state)
        user_id = _normalize_optional_string(state.get("user_id"))
        organization_id = _normalize_optional_string(state.get("organization_id"))
        enabled_skill_ids = _normalize_unique_strings(state.get("enabled_skill_ids", []))
        if not user_id or not organization_id or not enabled_skill_ids:
            return await handler(request)

        resolver = self.skill_access_resolver or _get_lead_agent_skill_access_resolver()
        enabled_skills = await resolver.resolve_skill_definitions(
            user_id=user_id,
            organization_id=organization_id,
            skill_ids=enabled_skill_ids,
        )
        if not enabled_skills:
            return await handler(request)

        prompt_sections = [
            _render_enabled_skill_summaries(enabled_skills),
        ]
        active_skill_id = _normalize_optional_string(state.get("active_skill_id"))
        if active_skill_id:
            active_skill = next(
                (skill for skill in enabled_skills if skill.skill_id == active_skill_id),
                None,
            )
            if active_skill is not None:
                prompt_sections.append(_render_active_skill_prompt(active_skill))

        updated_request = request.override(
            system_message=SystemMessage(
                content=_merge_system_prompt(
                    request.system_prompt,
                    prompt_sections,
                )
            )
        )
        return await handler(updated_request)


class LeadAgentToolSelectionMiddleware(AgentMiddleware[LeadAgentState, None, Any]):
    """Filter visible tools to the base or active-skill subset for each call."""

    state_schema = LeadAgentState
    tools: Sequence[BaseTool] = ()

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler,
    ) -> ModelResponse[Any]:
        state = _as_state_dict(request.state)
        enabled_skill_ids = _normalize_unique_strings(state.get("enabled_skill_ids", []))
        active_skill_id = _normalize_optional_string(state.get("active_skill_id"))
        allowed_tool_names = _normalize_unique_strings(state.get("allowed_tool_names", []))

        visible_tool_names = _visible_tool_names(
            enabled_skill_ids=enabled_skill_ids,
            active_skill_id=active_skill_id,
            allowed_tool_names=allowed_tool_names,
        )
        filtered_tools = [
            tool
            for tool in request.tools
            if _tool_name(tool) in visible_tool_names
        ]
        return await handler(request.override(tools=filtered_tools))


def _render_enabled_skill_summaries(skills: Sequence[Any]) -> str:
    """Build the lightweight skill discovery prompt section."""
    lines = [
        "You can load one of these internal lead-agent skills when the user's request needs specialized behavior.",
        "Call `load_skill` with the exact `skill_id` before using a skill.",
        "Available skills:",
    ]
    for skill in skills:
        lines.append(
            f"- skill_id: {skill.skill_id} | name: {skill.name} | summary: {skill.description}"
        )
    return "\n".join(lines)


def _render_active_skill_prompt(skill: Any) -> str:
    """Build the activated skill prompt section."""
    return "\n".join(
        [
            f"Active skill: {skill.skill_id} (version {skill.version})",
            "Activated instructions:",
            skill.activation_prompt.strip(),
        ]
    ).strip()


def _visible_tool_names(
    *,
    enabled_skill_ids: Sequence[str],
    active_skill_id: str | None,
    allowed_tool_names: Sequence[str],
) -> set[str]:
    """Resolve the visible tool names for the current model call."""
    if not enabled_skill_ids:
        return set()
    if not active_skill_id:
        return set(_BASE_SKILL_TOOL_NAMES)
    return set(_BASE_SKILL_TOOL_NAMES).union(allowed_tool_names)


def _tool_name(tool: BaseTool | dict[str, Any]) -> str | None:
    """Return a comparable tool name from a model request tool entry."""
    if isinstance(tool, dict):
        name = tool.get("name")
        if isinstance(name, str):
            return name
        return None
    return tool.name


def _merge_system_prompt(
    existing_prompt: str | None,
    prompt_sections: Sequence[str],
) -> str:
    """Merge the existing system prompt with skill-aware additions."""
    sections: list[str] = []
    if existing_prompt:
        sections.append(existing_prompt.strip())
    sections.extend(section.strip() for section in prompt_sections if section.strip())
    return "\n\n".join(sections)


def _as_state_dict(state: Any) -> dict[str, Any]:
    """Normalize middleware state into a plain dict."""
    if isinstance(state, dict):
        return state
    return dict(state)


def _normalize_optional_string(value: Any) -> str | None:
    """Normalize one optional string value."""
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def _normalize_unique_strings(values: Sequence[Any]) -> list[str]:
    """Normalize ordered strings while dropping blanks and duplicates."""
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized_value = str(value).strip()
        if not normalized_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values


def _get_lead_agent_skill_access_resolver() -> LeadAgentSkillAccessResolver:
    """Load the shared skill access resolver lazily to avoid import cycles."""
    from app.common.service import get_lead_agent_skill_access_resolver

    return get_lead_agent_skill_access_resolver()


LEAD_AGENT_MIDDLEWARE: list[AgentMiddleware[LeadAgentState, None, Any]] = [
    LeadAgentSkillPromptMiddleware(),
    LeadAgentToolSelectionMiddleware(),
]
