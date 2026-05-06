"""Shared helpers used across stock-agent middleware modules."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TYPE_CHECKING

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from app.services.ai.stock_agent_skill_access_resolver import (
        StockAgentSkillAccessResolver,
    )


def as_state_dict(state: Any) -> dict[str, Any]:
    """Normalize middleware state into a plain dict."""
    if isinstance(state, dict):
        return state
    return dict(state)


def normalize_optional_string(value: Any) -> str | None:
    """Normalize one optional string value."""
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def normalize_bool(value: Any) -> bool:
    """Normalize one flag-like value into a strict boolean."""
    return value is True


def normalize_non_negative_int(value: Any) -> int:
    """Normalize one optional numeric value into a non-negative integer."""
    try:
        normalized_value = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, normalized_value)


def normalize_unique_strings(values: Sequence[Any]) -> list[str]:
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


def tool_name(tool: BaseTool | dict[str, Any]) -> str | None:
    """Return a comparable tool name from a model request tool entry."""
    if isinstance(tool, dict):
        name = tool.get("name")
        if isinstance(name, str):
            return name
        return None
    return tool.name


def merge_system_prompt(
    existing_prompt: str | None,
    prompt_sections: Sequence[str],
) -> str:
    """Merge the existing system prompt with appended prompt sections."""
    sections: list[str] = []
    if existing_prompt:
        sections.append(existing_prompt.strip())
    sections.extend(section.strip() for section in prompt_sections if section.strip())
    return "\n\n".join(sections)


def get_stock_agent_skill_access_resolver() -> "StockAgentSkillAccessResolver":
    """Load the shared skill access resolver lazily to avoid import cycles."""
    from app.common.service import get_stock_agent_skill_access_resolver

    return get_stock_agent_skill_access_resolver()
