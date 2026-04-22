"""Tool surface helpers for the stock research runtime."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from app.common.exceptions import AppException
from app.infrastructure.mcp.manager import get_mcp_tools_manager
from app.infrastructure.mcp.research_tools import RESEARCH_TOOL_NAMES


@dataclass(frozen=True)
class StockResearchToolSurface:
    """Resolved normalized MCP tools used by the stock research runtime."""

    search: BaseTool
    fetch_content: BaseTool
    tools: tuple[BaseTool, BaseTool]


def get_stock_research_tool_surface() -> StockResearchToolSurface:
    """Resolve the required normalized MCP research tools for stock research."""
    mcp_manager = get_mcp_tools_manager()
    tools_by_name = {
        tool.name: tool
        for tool in mcp_manager.get_tools(tool_names=list(RESEARCH_TOOL_NAMES))
    }

    search_tool = tools_by_name.get("search")
    fetch_content_tool = tools_by_name.get("fetch_content")

    missing_capabilities: list[str] = []
    if search_tool is None:
        missing_capabilities.append("search")
    if fetch_content_tool is None:
        missing_capabilities.append("fetch_content")

    if missing_capabilities:
        missing_list = ", ".join(missing_capabilities)
        raise AppException(
            f"Stock research agent requires MCP research tools: {missing_list}"
        )

    return StockResearchToolSurface(
        search=search_tool,
        fetch_content=fetch_content_tool,
        tools=(search_tool, fetch_content_tool),
    )
