"""MCP (Model Context Protocol) server configuration.

This module defines configuration for MCP servers that provide tools
to AI agents (e.g., web search, content fetching).
"""

from typing import Literal, Optional, TypedDict


class StdioTransportConfig(TypedDict):
    """Configuration for MCP server using stdio transport.

    The server is spawned as a subprocess and communicates via stdin/stdout.
    """

    transport: Literal["stdio"]
    command: str
    args: list[str]
    enabled: bool


class HttpTransportConfig(TypedDict):
    """Configuration for MCP server using HTTP transport.

    The server is accessed via HTTP requests (for future use).
    """

    transport: Literal["http"]
    url: str
    headers: Optional[dict[str, str]]
    enabled: bool


# Union type for all supported MCP server configurations
MCPServerConfig = StdioTransportConfig | HttpTransportConfig


# MCP Server configurations
# Each server provides tools that can be used by AI agents
MCP_SERVERS: dict[str, MCPServerConfig] = {
    "ddg-search": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["duckduckgo-mcp-server"],
        "enabled": True,
    },
}


def get_enabled_mcp_servers() -> dict[str, MCPServerConfig]:
    """Get only enabled MCP server configurations.

    Returns:
        Dictionary of enabled MCP server configs with 'enabled' key removed.
    """
    return {
        name: config
        for name, config in MCP_SERVERS.items()
        if config.get("enabled", True)
    }


def get_mcp_client_config() -> dict[str, dict]:
    """Get MCP configuration formatted for MultiServerMCPClient.

    Removes the 'enabled' key as it's not needed by the client.

    Returns:
        Dictionary of server configs ready for MultiServerMCPClient.
    """
    enabled_servers = get_enabled_mcp_servers()
    return {
        name: {k: v for k, v in config.items() if k != "enabled"}
        for name, config in enabled_servers.items()
    }
