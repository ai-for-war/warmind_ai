"""Shared tool output limiting middleware."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

FETCH_CONTENT_MAX_CHARS = 4096
DEFAULT_LIMITED_TOOL_NAMES = ("fetch_content",)


class ToolOutputLimitMiddleware(AgentMiddleware[Any, None, Any]):
    """Hard-cap selected tool results before they enter model context."""

    tools: Sequence[BaseTool] = ()

    def __init__(
        self,
        *,
        max_chars: int = FETCH_CONTENT_MAX_CHARS,
        tool_names: Sequence[str] = DEFAULT_LIMITED_TOOL_NAMES,
    ) -> None:
        self.max_chars = max_chars
        self.tool_names = frozenset(tool_names)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ) -> ToolMessage | Command[Any]:
        response = await handler(request)
        tool_name = _tool_call_name(request.tool_call) or _registered_tool_name(
            request.tool
        )
        if (
            tool_name not in self.tool_names
            or not isinstance(response, ToolMessage)
            or response.status == "error"
        ):
            return response

        content = response.content
        if not isinstance(content, str):
            return response
        truncated_content = _truncate_tool_content(content, max_chars=self.max_chars)
        if truncated_content == content:
            return response
        return _copy_tool_message(response, content=truncated_content)


def _tool_call_name(tool_call: dict[str, Any]) -> str | None:
    """Return the model-requested tool name from one tool-call payload."""
    name = tool_call.get("name")
    if isinstance(name, str):
        return name
    return None


def _registered_tool_name(tool: BaseTool | None) -> str | None:
    """Return the registered tool object's name when available."""
    if tool is None:
        return None
    return tool.name


def _truncate_tool_content(content: str, *, max_chars: int) -> str:
    """Return content capped to max_chars, including a truncation marker."""
    if len(content) <= max_chars:
        return content

    marker = (
        "\n\n[TRUNCATED] tool output exceeded "
        f"{max_chars} characters. Original length: {len(content)} characters."
    )
    if len(marker) >= max_chars:
        return marker[:max_chars]

    return f"{content[: max_chars - len(marker)]}{marker}"


def _copy_tool_message(message: ToolMessage, **update: Any) -> ToolMessage:
    """Clone one tool message while preserving metadata fields."""
    if hasattr(message, "model_copy"):
        return message.model_copy(update=update)
    return message.copy(update=update)
