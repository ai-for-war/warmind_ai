"""Shared selectable tool catalog for stock-agent runtime and public APIs."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from app.agents.implementations.stock_agent.tools import STOCK_AGENT_INTERNAL_TOOLS
from app.infrastructure.mcp.manager import get_mcp_tools_manager
from app.infrastructure.mcp.research_tools import RESEARCH_TOOL_NAMES


@dataclass(frozen=True)
class StockAgentSelectableToolDescriptor:
    """Public metadata for one selectable stock-agent tool."""

    tool_name: str
    display_name: str
    description: str
    category: str


@dataclass(frozen=True)
class _StockAgentSelectableToolRegistration:
    """Internal registration entry linking tool metadata to runtime tools."""

    descriptor: StockAgentSelectableToolDescriptor
    tool: BaseTool


def _get_selectable_tool_registrations() -> list[_StockAgentSelectableToolRegistration]:
    """Resolve the currently available selectable stock-agent tools."""
    registrations: list[_StockAgentSelectableToolRegistration] = []

    mcp_manager = get_mcp_tools_manager()
    mcp_tools = {
        tool.name: tool
        for tool in mcp_manager.get_tools(tool_names=list(RESEARCH_TOOL_NAMES))
    }

    search_tool = mcp_tools.get("search")
    if search_tool is not None:
        registrations.append(
            _StockAgentSelectableToolRegistration(
                descriptor=StockAgentSelectableToolDescriptor(
                    tool_name="search",
                    display_name="Web Search",
                    description="Search the web for current external information.",
                    category="research",
                ),
                tool=search_tool,
            )
        )

    fetch_content_tool = mcp_tools.get("fetch_content")
    if fetch_content_tool is not None:
        registrations.append(
            _StockAgentSelectableToolRegistration(
                descriptor=StockAgentSelectableToolDescriptor(
                    tool_name="fetch_content",
                    display_name="Fetch Web Content",
                    description="Fetch and extract content from a specific web page URL.",
                    category="research",
                ),
                tool=fetch_content_tool,
            )
        )

    return registrations


def get_stock_agent_selectable_tool_catalog() -> list[StockAgentSelectableToolDescriptor]:
    """Return the selectable tool catalog that is actually available."""
    return [
        registration.descriptor for registration in _get_selectable_tool_registrations()
    ]


def get_stock_agent_selectable_tool_names() -> set[str]:
    """Return the set of selectable tool names currently available."""
    return {
        descriptor.tool_name for descriptor in get_stock_agent_selectable_tool_catalog()
    }


def get_stock_agent_tools() -> list[BaseTool]:
    """Return the full runtime tool surface for stock-agent."""
    return STOCK_AGENT_INTERNAL_TOOLS + [
        registration.tool for registration in _get_selectable_tool_registrations()
    ]
