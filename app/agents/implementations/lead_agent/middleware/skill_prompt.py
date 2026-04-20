"""Skill prompt middleware for the lead-agent runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from app.agents.implementations.lead_agent.state import LeadAgentState
from app.agents.implementations.lead_agent.middleware.shared import (
    as_state_dict,
    get_lead_agent_skill_access_resolver,
    merge_system_prompt,
    normalize_optional_string,
    normalize_unique_strings,
)
from app.services.ai.lead_agent_skill_access_resolver import (
    LeadAgentSkillAccessResolver,
)


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
        state = as_state_dict(request.state)
        user_id = normalize_optional_string(state.get("user_id"))
        organization_id = normalize_optional_string(state.get("organization_id"))
        enabled_skill_ids = normalize_unique_strings(state.get("enabled_skill_ids", []))
        if not user_id or not organization_id or not enabled_skill_ids:
            return await handler(request)

        resolver = self.skill_access_resolver or get_lead_agent_skill_access_resolver()
        enabled_skills = await resolver.resolve_skill_definitions(
            user_id=user_id,
            organization_id=organization_id,
            skill_ids=enabled_skill_ids,
        )
        if not enabled_skills:
            return await handler(request)

        prompt_sections = [_render_enabled_skill_summaries(enabled_skills)]
        active_skill_id = normalize_optional_string(state.get("active_skill_id"))
        if active_skill_id:
            active_skill = next(
                (
                    skill
                    for skill in enabled_skills
                    if skill.skill_id == active_skill_id
                ),
                None,
            )
            if active_skill is not None:
                prompt_sections.append(_render_active_skill_prompt(active_skill))

        updated_request = request.override(
            system_message=SystemMessage(
                content=merge_system_prompt(
                    request.system_prompt,
                    prompt_sections,
                )
            )
        )
        return await handler(updated_request)


def _render_enabled_skill_summaries(skills: Sequence[Any]) -> str:
    """Build the lightweight skill discovery prompt section."""
    skills_list = []
    for skill in skills:
        skills_list.append(
            f"- skill_id: {skill.skill_id} | name: {skill.name} | summary: {skill.description}"
        )
    if skills_list:
        skills_list = "\n".join(skills_list)
    else:
        skills_list = "No skills available."
    lines = """
    <Skill_system>
    You have access to skills that provide optimized workflows for specific tasks. Each skill contains best practices, frameworks, and references to additional resources.
    **Progressive Loading Pattern:**
    1. When the user's query relates to a skill summary, immediately call the `load_skill` function with the correct `skill_id` to load that skill.
    2. Follow the skill's instructions precisely
    <Available Skills>
    {skills_list}
    </Available Skills>
    </Skill_system>
    """

    return lines.format(skills_list=skills_list)


def _render_active_skill_prompt(skill: Any) -> str:
    """Build the activated skill prompt section."""
    return f"""
    <Active_skill>
    Active skill: {skill.skill_id} (version {skill.version})
    Activated instructions:
    {skill.activation_prompt.strip()}
    </Active_skill>
    """
