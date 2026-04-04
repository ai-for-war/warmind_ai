"""Normalization helpers for MCP-based research tools.

This module keeps the application-facing web research contract stable even
when upstream MCP providers expose different tool names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from langchain_core.tools import BaseTool

# Stable app-level research capabilities and their provider-specific aliases.
RESEARCH_TOOL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "search": ("search", "search_text"),
    "fetch_content": ("fetch_content", "extract_content"),
}


@dataclass(frozen=True)
class NormalizedMCPTools:
    """Normalized tool view built from raw MCP tools."""

    tools: list[BaseTool]
    raw_tools: list[BaseTool]
    normalized_mapping: dict[str, str]
    missing_capabilities: list[str]


def normalize_mcp_tools(raw_tools: list[BaseTool]) -> NormalizedMCPTools:
    """Return one normalized MCP tool surface.

    Research tools are exposed under stable app-level names while every other
    non-research tool is passed through unchanged.
    """
    tools_by_name = {
        tool.name: tool
        for tool in raw_tools
        if getattr(tool, "name", None)
    }

    normalized_tools: list[BaseTool] = []
    normalized_mapping: dict[str, str] = {}
    consumed_raw_tool_names: set[str] = set()
    missing_capabilities: list[str] = []

    for normalized_name, candidate_names in RESEARCH_TOOL_CANDIDATES.items():
        raw_tool = next(
            (tools_by_name[candidate] for candidate in candidate_names if candidate in tools_by_name),
            None,
        )
        if raw_tool is None:
            missing_capabilities.append(normalized_name)
            continue

        consumed_raw_tool_names.add(raw_tool.name)
        normalized_mapping[normalized_name] = raw_tool.name
        normalized_tools.append(_normalize_tool(raw_tool, normalized_name))

    passthrough_tools = [
        tool for tool in raw_tools if tool.name not in consumed_raw_tool_names
    ]

    return NormalizedMCPTools(
        tools=normalized_tools + passthrough_tools,
        raw_tools=list(raw_tools),
        normalized_mapping=normalized_mapping,
        missing_capabilities=missing_capabilities,
    )


def _normalize_tool(tool: BaseTool, normalized_name: str) -> BaseTool:
    """Return the tool directly or as a renamed clone for app-level use."""
    if tool.name == normalized_name:
        return tool
    return _clone_tool(tool, name=normalized_name)


def _clone_tool(tool: BaseTool, **update: Any) -> BaseTool:
    """Clone one LangChain tool with small field overrides."""
    if hasattr(tool, "model_copy"):
        return cast(BaseTool, tool.model_copy(update=update))
    if hasattr(tool, "copy"):
        return cast(BaseTool, tool.copy(update=update))

    msg = (
        f"Unable to clone MCP tool '{tool.name}' for normalization because "
        f"its type '{type(tool).__name__}' does not support model_copy/copy."
    )
    raise TypeError(msg)
