"""MCP (Model Context Protocol) infrastructure module.

This module provides the MCPToolsManager for managing MCP server connections
and exposing tools to AI agents.
"""

from app.infrastructure.mcp.manager import MCPToolsManager, get_mcp_tools_manager

__all__ = ["MCPToolsManager", "get_mcp_tools_manager"]
