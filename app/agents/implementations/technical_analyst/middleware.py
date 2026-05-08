"""Middleware helpers for the technical analyst runtime."""

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
from app.prompts.system.technical_analyst import (
    get_technical_analyst_summarization_prompt,
)

TECHNICAL_ANALYST_SUMMARIZATION_TOKEN_TRIGGER = ("tokens", 16384)
TECHNICAL_ANALYST_SUMMARIZATION_FRACTION_TRIGGER = ("fraction", 0.7)
TECHNICAL_ANALYST_SUMMARIZATION_KEEP = ("messages", 2)
TECHNICAL_ANALYST_SUMMARIZATION_TRIM_TOKENS = 16384
TECHNICAL_ANALYST_TOOL_OUTPUT_MAX_ESTIMATED_TOKENS = 3000
TECHNICAL_ANALYST_LIMITED_TOOL_NAMES = ("load_price_history",)


def _build_technical_analyst_summarization_triggers(
    model: BaseChatModel,
) -> list[tuple[str, int | float]]:
    """Build safe technical analyst summary triggers for one resolved model."""
    triggers: list[tuple[str, int | float]] = [
        TECHNICAL_ANALYST_SUMMARIZATION_TOKEN_TRIGGER,
    ]
    profile = getattr(model, "profile", None)
    if isinstance(profile, dict) and isinstance(profile.get("max_input_tokens"), int):
        triggers.insert(0, TECHNICAL_ANALYST_SUMMARIZATION_FRACTION_TRIGGER)
    return triggers


def build_technical_analyst_middleware(
    model: BaseChatModel,
) -> list[AgentMiddleware[Any, None, Any]]:
    """Build the ordered technical analyst middleware stack for one model."""
    return [
        SummarizationMiddleware(
            model=model,
            trigger=_build_technical_analyst_summarization_triggers(model),
            keep=TECHNICAL_ANALYST_SUMMARIZATION_KEEP,
            summary_prompt=get_technical_analyst_summarization_prompt(),
            trim_tokens_to_summarize=TECHNICAL_ANALYST_SUMMARIZATION_TRIM_TOKENS,
        ),
        ToolOutputLimitMiddleware(
            max_estimated_tokens=TECHNICAL_ANALYST_TOOL_OUTPUT_MAX_ESTIMATED_TOKENS,
            tool_names=TECHNICAL_ANALYST_LIMITED_TOOL_NAMES,
        ),
        TechnicalAnalystToolErrorMiddleware(),
    ]


class TechnicalAnalystToolErrorMiddleware(
    AgentMiddleware[dict[str, Any], None, Any]
):
    """Convert deterministic technical-analysis tool failures into bounded messages."""

    tools: Sequence[BaseTool] = ()

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ) -> ToolMessage:
        try:
            return await handler(request)
        except ToolException as exc:
            return _tool_error_message(request, str(exc))
        except Exception as exc:
            return _tool_error_message(request, str(exc) or exc.__class__.__name__)


def _tool_error_message(request: ToolCallRequest, detail: str) -> ToolMessage:
    failed_tool_name = _tool_name(request.tool) or _tool_name(request.tool_call) or "tool"
    bounded_detail = detail.strip()[:800] or "unknown error"
    error_message = (
        f"Tool '{failed_tool_name}' failed: {bounded_detail}. "
        "Continue with available technical evidence and state the limitation in "
        "`uncertainties`; do not fabricate missing indicator or backtest values."
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
