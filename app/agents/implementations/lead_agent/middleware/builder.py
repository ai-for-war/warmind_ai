"""Middleware stack builder for the lead-agent runtime."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, SummarizationMiddleware
from langchain.chat_models import BaseChatModel

from app.agents.implementations.lead_agent.middleware.constants import (
    LEAD_AGENT_SUMMARIZATION_FRACTION_TRIGGER,
    LEAD_AGENT_SUMMARIZATION_KEEP,
    LEAD_AGENT_SUMMARIZATION_MESSAGE_TRIGGER,
    LEAD_AGENT_SUMMARIZATION_TOKEN_TRIGGER,
    LEAD_AGENT_SUMMARIZATION_TRIM_TOKENS,
)
from app.agents.implementations.lead_agent.middleware.delegation_limit import (
    LeadAgentDelegationLimitMiddleware,
)
from app.agents.implementations.lead_agent.middleware.orchestration import (
    LeadAgentOrchestrationPromptMiddleware,
)
from app.agents.implementations.lead_agent.middleware.skill_prompt import (
    LeadAgentSkillPromptMiddleware,
)
from app.agents.implementations.lead_agent.middleware.todo import (
    LeadAgentTodoMiddleware,
)
from app.agents.implementations.lead_agent.middleware.tool_error import (
    LeadAgentToolErrorMiddleware,
)
from app.agents.implementations.lead_agent.middleware.tool_selection import (
    LeadAgentToolSelectionMiddleware,
)
from app.prompts.system.lead_agent import get_lead_agent_summarization_prompt


def _build_lead_agent_summarization_triggers(
    model: BaseChatModel,
) -> list[tuple[str, int | float]]:
    """Build safe trigger thresholds for one resolved model profile."""
    triggers: list[tuple[str, int | float]] = [
        LEAD_AGENT_SUMMARIZATION_MESSAGE_TRIGGER,
        LEAD_AGENT_SUMMARIZATION_TOKEN_TRIGGER,
    ]
    profile = getattr(model, "profile", None)
    if isinstance(profile, dict) and isinstance(profile.get("max_input_tokens"), int):
        triggers.insert(0, LEAD_AGENT_SUMMARIZATION_FRACTION_TRIGGER)
    return triggers


def build_lead_agent_middleware(
    model: BaseChatModel,
) -> list[AgentMiddleware[Any, None, Any]]:
    """Build the ordered lead-agent middleware stack for one resolved model."""
    return [
        SummarizationMiddleware(
            model=model,
            trigger=_build_lead_agent_summarization_triggers(model),
            keep=LEAD_AGENT_SUMMARIZATION_KEEP,
            summary_prompt=get_lead_agent_summarization_prompt(),
            trim_tokens_to_summarize=LEAD_AGENT_SUMMARIZATION_TRIM_TOKENS,
        ),
        LeadAgentOrchestrationPromptMiddleware(),
        LeadAgentSkillPromptMiddleware(),
        LeadAgentTodoMiddleware(),
        LeadAgentDelegationLimitMiddleware(),
        LeadAgentToolSelectionMiddleware(),
        LeadAgentToolErrorMiddleware(),
    ]
