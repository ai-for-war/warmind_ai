"""Shared tool output limiting middleware."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

FETCH_CONTENT_MAX_ESTIMATED_TOKENS = 3000
FETCH_CONTENT_TOKEN_ENCODING = "o200k_base"
DEFAULT_LIMITED_TOOL_NAMES = ("fetch_content",)

logger = logging.getLogger(__name__)


class ToolOutputLimitMiddleware(AgentMiddleware[Any, None, Any]):
    """Hard-cap selected tool results before they enter model context."""

    tools: Sequence[BaseTool] = ()

    def __init__(
        self,
        *,
        max_estimated_tokens: int = FETCH_CONTENT_MAX_ESTIMATED_TOKENS,
        tool_names: Sequence[str] = DEFAULT_LIMITED_TOOL_NAMES,
    ) -> None:
        if max_estimated_tokens <= 0:
            raise ValueError("max_estimated_tokens must be greater than 0")
        self.max_estimated_tokens = max_estimated_tokens
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
        logger.info("Tool call completed: %s.", tool_name or "unknown")

        if (
            tool_name not in self.tool_names
            or not isinstance(response, ToolMessage)
            or response.status == "error"
        ):
            return response

        content = response.content
        content_text = _content_to_text(content)
        if content_text is None:
            return response

        truncated_content, was_truncated = _truncate_tool_content_by_estimated_tokens(
            content_text,
            max_estimated_tokens=self.max_estimated_tokens,
        )
        if not was_truncated:
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


def _truncate_tool_content_by_estimated_tokens(
    content: str,
    *,
    max_estimated_tokens: int,
) -> tuple[str, bool]:
    """Return content capped to estimated tokens, including a marker."""
    encoding = _get_tiktoken_encoding()
    if encoding is None:
        return content, False

    tokens = encoding.encode(content)
    logger.info(
        "Truncating tool output: max_estimated_tokens=%d content_estimated_tokens=%d",
        max_estimated_tokens,
        len(tokens),
    )
    if len(tokens) <= max_estimated_tokens:
        return content, False

    marker = (
        "\n\n[TRUNCATED] tool output exceeded "
        f"{max_estimated_tokens} estimated tokens using "
        f"{FETCH_CONTENT_TOKEN_ENCODING}. Original estimated tokens: {len(tokens)}."
    )
    marker_tokens = encoding.encode(marker)
    if len(marker_tokens) >= max_estimated_tokens:
        return encoding.decode(marker_tokens[:max_estimated_tokens]), True

    content_token_budget = max_estimated_tokens - len(marker_tokens)
    return encoding.decode(tokens[:content_token_budget] + marker_tokens), True


def _content_to_text(content: Any) -> str | None:
    """Convert supported ToolMessage content shapes into text for limiting."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_content_block_to_text(item) for item in content)
    return None


def _content_block_to_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        text = item.get("text")
        if isinstance(text, str):
            return text
        return json.dumps(item, ensure_ascii=False, default=str)
    return str(item)


def _count_tokens(content: str) -> int | None:
    """Return a tokenizer-based token count when tiktoken is available."""
    encoding = _get_tiktoken_encoding()
    if encoding is None:
        return None
    return len(encoding.encode(content))


@lru_cache(maxsize=1)
def _get_tiktoken_encoding() -> Any | None:
    try:
        import tiktoken
    except ImportError:
        return None
    return tiktoken.get_encoding(FETCH_CONTENT_TOKEN_ENCODING)


def _copy_tool_message(message: ToolMessage, **update: Any) -> ToolMessage:
    """Clone one tool message while preserving metadata fields."""
    if hasattr(message, "model_copy"):
        return message.model_copy(update=update)
    return message.copy(update=update)
