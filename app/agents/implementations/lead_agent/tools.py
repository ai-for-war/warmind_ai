"""Lead-agent tool registry for the skill-aware runtime."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.types import Command

from app.services.ai.lead_agent_skill_access_resolver import (
    LeadAgentSkillAccessResolver,
)

logger = logging.getLogger(__name__)


@tool("load_skill", parse_docstring=True)
async def load_skill(skill_id: str, runtime: ToolRuntime) -> Command:
    """Load one enabled lead-agent skill into the active runtime state.

    Args:
        skill_id: The ID of the skill to load..
    """
    return await _load_skill_command(
        skill_id=skill_id,
        runtime=runtime,
        skill_access_resolver=_get_lead_agent_skill_access_resolver(),
    )


async def _load_skill_command(
    *,
    skill_id: str,
    runtime: ToolRuntime,
    skill_access_resolver: LeadAgentSkillAccessResolver,
) -> Command:
    """Validate and activate one lead-agent skill for the current thread."""
    normalized_skill_id = skill_id.strip()
    state = _as_state_dict(runtime.state)
    enabled_skill_ids = _normalize_unique_strings(state.get("enabled_skill_ids", []))

    if not normalized_skill_id or normalized_skill_id not in enabled_skill_ids:
        logger.warning(
            "Rejected lead-agent skill load for unavailable skill '%s' (user_id=%s, organization_id=%s)",
            normalized_skill_id or skill_id,
            state.get("user_id"),
            state.get("organization_id"),
        )
        return _tool_acknowledgement(
            runtime,
            f"Skill '{normalized_skill_id or skill_id}' is not available for this thread.",
        )

    user_id = state.get("user_id")
    organization_id = state.get("organization_id")
    if not user_id or organization_id is None:
        logger.warning(
            "Rejected lead-agent skill load for incomplete caller scope (skill_id=%s, user_id=%s, organization_id=%s)",
            normalized_skill_id,
            user_id,
            organization_id,
        )
        return _tool_acknowledgement(
            runtime,
            f"Skill '{normalized_skill_id}' is not available for this thread.",
        )

    skill = await skill_access_resolver.resolve_enabled_skill_for_caller(
        user_id=str(user_id),
        organization_id=str(organization_id),
        skill_id=normalized_skill_id,
    )
    if skill is None:
        logger.warning(
            "Lead-agent skill '%s' was enabled in thread state but not accessible in storage (user_id=%s, organization_id=%s)",
            normalized_skill_id,
            user_id,
            organization_id,
        )
        return _tool_acknowledgement(
            runtime,
            f"Skill '{normalized_skill_id}' is not available for this thread.",
        )

    loaded_skills = _append_unique(
        state.get("loaded_skills", []),
        skill.skill_id,
    )
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"Loaded skill '{skill.skill_id}' (v{skill.version}).",
                    tool_call_id=_tool_call_id(runtime),
                )
            ],
            "active_skill_id": skill.skill_id,
            "loaded_skills": loaded_skills,
            "allowed_tool_names": _normalize_skill_tool_names(skill.allowed_tool_names),
            "active_skill_version": skill.version,
        }
    )


def _tool_acknowledgement(runtime: ToolRuntime, content: str) -> Command:
    """Build a command that only appends the tool acknowledgement message."""
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=_tool_call_id(runtime),
                )
            ]
        }
    )


def _tool_call_id(runtime: ToolRuntime) -> str:
    """Return the current tool-call identifier or a safe fallback for tests."""
    return runtime.tool_call_id or "load_skill"


def _append_unique(values: Sequence[Any], new_value: str) -> list[str]:
    """Append one normalized string while preserving existing order."""
    normalized_values = _normalize_unique_strings(values)
    normalized_new_value = new_value.strip()
    if normalized_new_value and normalized_new_value not in normalized_values:
        normalized_values.append(normalized_new_value)
    return normalized_values


def _normalize_skill_tool_names(tool_names: Sequence[Any]) -> list[str]:
    """Normalize the tool names granted by a loaded skill."""
    return _normalize_unique_strings(tool_names)


def _normalize_unique_strings(values: Sequence[Any]) -> list[str]:
    """Normalize one ordered list of strings and drop blanks/duplicates."""
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized_value = str(value).strip()
        if not normalized_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values


def _as_state_dict(state: Any) -> dict[str, Any]:
    """Normalize tool runtime state into a plain dict."""
    if isinstance(state, dict):
        return state
    return dict(state)


def _get_lead_agent_skill_access_resolver() -> LeadAgentSkillAccessResolver:
    """Load the shared skill access resolver lazily to avoid import cycles."""
    from app.common.service import get_lead_agent_skill_access_resolver

    return get_lead_agent_skill_access_resolver()


LEAD_AGENT_INTERNAL_TOOLS: list[BaseTool] = [load_skill]
