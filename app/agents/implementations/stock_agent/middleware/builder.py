"""Middleware stack builder for the stock-agent runtime."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, SummarizationMiddleware
from langchain.chat_models import BaseChatModel

from app.agents.middleware.tool_output_limit import ToolOutputLimitMiddleware
from app.agents.implementations.stock_agent.middleware.constants import (
    STOCK_AGENT_SUMMARIZATION_FRACTION_TRIGGER,
    STOCK_AGENT_SUMMARIZATION_KEEP,
    STOCK_AGENT_SUMMARIZATION_MESSAGE_TRIGGER,
    STOCK_AGENT_SUMMARIZATION_TOKEN_TRIGGER,
    STOCK_AGENT_SUMMARIZATION_TRIM_TOKENS,
)
from app.agents.implementations.stock_agent.middleware.orchestration import (
    StockAgentOrchestrationPromptMiddleware,
)
from app.agents.implementations.stock_agent.middleware.skill_prompt import (
    StockAgentSkillPromptMiddleware,
)
from app.agents.implementations.stock_agent.middleware.todo import (
    StockAgentTodoMiddleware,
)
from app.agents.implementations.stock_agent.middleware.tool_error import (
    StockAgentToolErrorMiddleware,
)
from app.agents.implementations.stock_agent.middleware.tool_selection import (
    StockAgentToolSelectionMiddleware,
)
from app.prompts.system.stock_agent import get_stock_agent_summarization_prompt


def _build_stock_agent_summarization_triggers(
    model: BaseChatModel,
) -> list[tuple[str, int | float]]:
    """Build safe trigger thresholds for one resolved model profile."""
    triggers: list[tuple[str, int | float]] = [
        STOCK_AGENT_SUMMARIZATION_MESSAGE_TRIGGER,
        STOCK_AGENT_SUMMARIZATION_TOKEN_TRIGGER,
    ]
    profile = getattr(model, "profile", None)
    if isinstance(profile, dict) and isinstance(profile.get("max_input_tokens"), int):
        triggers.insert(0, STOCK_AGENT_SUMMARIZATION_FRACTION_TRIGGER)
    return triggers


def build_stock_agent_middleware(
    model: BaseChatModel,
) -> list[AgentMiddleware[Any, None, Any]]:
    """Build the ordered stock-agent middleware stack for one resolved model."""
    return [
        SummarizationMiddleware(
            model=model,
            trigger=_build_stock_agent_summarization_triggers(model),
            keep=STOCK_AGENT_SUMMARIZATION_KEEP,
            summary_prompt=get_stock_agent_summarization_prompt(),
            trim_tokens_to_summarize=STOCK_AGENT_SUMMARIZATION_TRIM_TOKENS,
        ),
        StockAgentOrchestrationPromptMiddleware(),
        StockAgentSkillPromptMiddleware(),
        StockAgentTodoMiddleware(),
        StockAgentToolSelectionMiddleware(),
        ToolOutputLimitMiddleware(),
        StockAgentToolErrorMiddleware(),
    ]
