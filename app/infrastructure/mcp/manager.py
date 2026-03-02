"""MCP Tools Manager for managing MCP server connections and tools.

This module provides a singleton manager that initializes MCP servers
and exposes their tools to AI agents.
"""

import asyncio
import logging
from functools import lru_cache
from typing import Optional

from langchain_core.tools import BaseTool

from app.config.mcp import MCPServerConfig

logger = logging.getLogger(__name__)

# Timeout for MCP initialization in seconds
MCP_INIT_TIMEOUT = 30


class MCPToolsManager:
    """Singleton manager for MCP server connections and tools.

    This class manages the lifecycle of MCP server connections and provides
    access to tools from all configured MCP servers.

    Attributes:
        _instance: Singleton instance of the manager.
        _client: MultiServerMCPClient instance.
        _tools: List of tools loaded from MCP servers.
        _initialized: Whether the manager has been initialized.
    """

    _instance: Optional["MCPToolsManager"] = None
    _client: Optional[object] = None  # MultiServerMCPClient
    _tools: list[BaseTool] = []
    _initialized: bool = False

    def __new__(cls) -> "MCPToolsManager":
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = []
            cls._instance._client = None
            cls._instance._initialized = False
        return cls._instance

    @classmethod
    def get_instance(cls) -> "MCPToolsManager":
        """Get the singleton instance of MCPToolsManager.

        Returns:
            The singleton MCPToolsManager instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance. Used for testing."""
        cls._instance = None

    async def initialize(
        self,
        config: dict[str, MCPServerConfig],
        timeout: float = MCP_INIT_TIMEOUT,
    ) -> None:
        """Initialize MCP client with configured servers.

        Filters out disabled servers and initializes connections to enabled ones.
        If initialization fails, logs the error and continues with empty tools.

        Args:
            config: Dictionary of MCP server configurations.
            timeout: Timeout in seconds for initialization. Defaults to 30.
        """
        try:
            # Import here to avoid import errors if package not installed
            from langchain_mcp_adapters.client import MultiServerMCPClient

            # Filter enabled servers and remove 'enabled' key
            enabled_servers = {
                name: {k: v for k, v in cfg.items() if k != "enabled"}
                for name, cfg in config.items()
                if cfg.get("enabled", True)
            }

            if not enabled_servers:
                logger.warning("No enabled MCP servers configured")
                self._tools = []
                self._initialized = True
                return

            logger.info(
                "Initializing MCP client with servers: %s",
                list(enabled_servers.keys()),
            )

            # Initialize client with timeout
            self._client = MultiServerMCPClient(enabled_servers)

            # Load tools with timeout
            self._tools = await asyncio.wait_for(
                self._client.get_tools(),
                timeout=timeout,
            )

            self._initialized = True
            logger.info(
                "MCP initialization complete. Loaded %d tools", len(self._tools)
            )

        except asyncio.TimeoutError:
            logger.error(
                "MCP initialization timed out after %d seconds. "
                "Continuing without MCP tools.",
                timeout,
            )
            self._tools = []
            self._initialized = True

        except ImportError as e:
            logger.error(
                "Failed to import langchain-mcp-adapters: %s. "
                "Ensure the package is installed.",
                e,
            )
            self._tools = []
            self._initialized = True

        except Exception as e:  # noqa: BLE001
            logger.error(
                "MCP initialization failed: %s. Continuing without MCP tools.", e
            )
            self._tools = []
            self._initialized = True

    def get_tools(
        self,
        tool_names: list[str] | None = None,
    ) -> list[BaseTool]:
        """Get MCP tools, optionally filtered by tool name.

        Args:
            tool_names: Optional list of tool names to filter by.
                Only tools with these names will be returned.
                Example: ["search", "fetch"] for web search tools.

        Returns:
            List of BaseTool instances from MCP servers.
            Returns empty list if not initialized or initialization failed.

        Examples:
            # Get all tools
            tools = manager.get_tools()

            # Get specific tools by name
            tools = manager.get_tools(tool_names=["search", "fetch"])
        """
        if not self._initialized:
            logger.warning("MCPToolsManager not initialized. Call initialize() first.")
            return []

        # No filtering, return all tools
        if tool_names is None:
            return self._tools

        # Filter by tool name
        return [tool for tool in self._tools if tool.name in tool_names]

    async def reload(
        self,
        config: dict[str, MCPServerConfig],
        timeout: float = MCP_INIT_TIMEOUT,
    ) -> None:
        """Reload MCP connections with new configuration.

        Closes existing connections and reinitializes with new config.

        Args:
            config: New MCP server configurations.
            timeout: Timeout in seconds for initialization. Defaults to 30.
        """
        logger.info("Reloading MCP connections...")

        # Close existing client if any
        if self._client is not None:
            try:
                # MultiServerMCPClient may have a close method
                if hasattr(self._client, "close"):
                    await self._client.close()
            except Exception as e:  # noqa: BLE001
                logger.warning("Error closing existing MCP client: %s", e)

        self._client = None
        self._tools = []
        self._initialized = False

        # Reinitialize with new config
        await self.initialize(config, timeout)

    @property
    def is_initialized(self) -> bool:
        """Check if the manager has been initialized.

        Returns:
            True if initialized, False otherwise.
        """
        return self._initialized

    @property
    def tool_count(self) -> int:
        """Get the number of loaded tools.

        Returns:
            Number of tools loaded from MCP servers.
        """
        return len(self._tools)


@lru_cache
def get_mcp_tools_manager() -> MCPToolsManager:
    """Get the singleton MCPToolsManager instance.

    This function is cached to ensure the same instance is returned
    on subsequent calls.

    Returns:
        The singleton MCPToolsManager instance.
    """
    return MCPToolsManager.get_instance()
