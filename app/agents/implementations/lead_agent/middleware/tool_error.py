"""Tool error middleware for the lead-agent runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, ToolException

from app.agents.implementations.lead_agent.middleware.shared import tool_name
from app.agents.implementations.lead_agent.state import LeadAgentState


class LeadAgentToolErrorMiddleware(AgentMiddleware[LeadAgentState, None, Any]):
    """Convert tool execution failures into tool messages so the run can continue."""

    state_schema = LeadAgentState
    tools: Sequence[BaseTool] = ()

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ) -> ToolMessage:
        try:
            return await handler(request)
        except ToolException as exc:
            failed_tool_name = tool_name(request.tool) or request.tool_call.get("name") or "tool"
            error_message = (
                f"Tool '{failed_tool_name}' failed: {exc}. "
                "Continue without this result and try another source if needed."
            )
            return ToolMessage(
                content=error_message,
                tool_call_id=str(request.tool_call.get("id") or failed_tool_name),
                status="error",
            )
