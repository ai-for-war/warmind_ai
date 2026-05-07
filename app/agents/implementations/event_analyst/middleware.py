"""Middleware helpers for the event analyst runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    SummarizationMiddleware,
    ToolCallRequest,
)
from langchain.chat_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, ToolException

from app.agents.middleware.tool_output_limit import ToolOutputLimitMiddleware
from app.prompts.system.event_analyst import (
    get_event_analyst_summarization_prompt,
)

EVENT_ANALYST_SUMMARIZATION_TOKEN_TRIGGER = ("tokens", 16384)
EVENT_ANALYST_SUMMARIZATION_FRACTION_TRIGGER = ("fraction", 0.7)
EVENT_ANALYST_SUMMARIZATION_KEEP = ("messages", 2)
EVENT_ANALYST_SUMMARIZATION_TRIM_TOKENS = 16384


def _build_event_analyst_summarization_triggers(
    model: BaseChatModel,
) -> list[tuple[str, int | float]]:
    """Build safe event analyst summary triggers for one resolved model."""
    triggers: list[tuple[str, int | float]] = [
        EVENT_ANALYST_SUMMARIZATION_TOKEN_TRIGGER,
    ]
    profile = getattr(model, "profile", None)
    if isinstance(profile, dict) and isinstance(profile.get("max_input_tokens"), int):
        triggers.insert(0, EVENT_ANALYST_SUMMARIZATION_FRACTION_TRIGGER)
    return triggers


def build_event_analyst_middleware(
    model: BaseChatModel,
) -> list[AgentMiddleware[Any, None, Any]]:
    """Build the ordered event analyst middleware stack for one model."""
    return [
        SummarizationMiddleware(
            model=model,
            trigger=_build_event_analyst_summarization_triggers(model),
            keep=EVENT_ANALYST_SUMMARIZATION_KEEP,
            summary_prompt=get_event_analyst_summarization_prompt(),
            trim_tokens_to_summarize=EVENT_ANALYST_SUMMARIZATION_TRIM_TOKENS,
        ),
        ToolOutputLimitMiddleware(),
        EventAnalystToolErrorMiddleware(),
    ]


class EventAnalystToolErrorMiddleware(AgentMiddleware[dict[str, Any], None, Any]):
    """Convert web research tool failures into bounded tool messages."""

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
                "Continue with available evidence and state the evidence gap."
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

