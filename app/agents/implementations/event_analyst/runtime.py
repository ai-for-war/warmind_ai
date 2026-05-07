"""Runtime helpers for event analyst execution."""

from __future__ import annotations

from app.agents.runtime import (
    AgentRuntimeConfig as EventAnalystRuntimeConfig,
    build_chat_model,
)

EVENT_ANALYST_MAX_TOKENS = 8192
EVENT_ANALYST_TEMPERATURE = 0.2


def build_event_analyst_model(
    runtime_config: EventAnalystRuntimeConfig,
) -> object:
    """Build the concrete LangChain chat model for one event analyst run."""
    return build_chat_model(
        runtime_config=runtime_config,
        agent_label="event-analyst",
        max_tokens=EVENT_ANALYST_MAX_TOKENS,
        temperature=EVENT_ANALYST_TEMPERATURE,
        streaming=False,
    )

