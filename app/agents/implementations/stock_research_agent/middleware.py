"""Middleware helpers for the stock-research agent runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, ToolException


class StockResearchToolErrorMiddleware(AgentMiddleware[dict[str, Any], None, Any]):
    """Convert tool failures into tool messages so research can continue."""

    tools: Sequence[BaseTool] = ()

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ) -> ToolMessage:
        try:
            return await handler(request)
        except ToolException as exc:
            failed_tool_name = _tool_name(request.tool) or _tool_name(
                request.tool_call
            ) or "tool"
            error_message = (
                f"Tool '{failed_tool_name}' failed: {exc}. "
                "Continue without this result and try another source if needed."
            )
            return ToolMessage(
                content=error_message,
                tool_call_id=str(request.tool_call.get("id") or failed_tool_name),
                status="error",
            )


def _tool_name(tool: BaseTool | dict[str, Any]) -> str | None:
    """Return a comparable tool name from one tool or tool-call payload."""
    if isinstance(tool, dict):
        name = tool.get("name")
        if isinstance(name, str):
            return name
        return None
    return tool.name
