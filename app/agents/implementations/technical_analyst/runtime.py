"""Runtime helpers for technical analyst execution."""

from __future__ import annotations

from app.agents.runtime import (
    AgentRuntimeConfig as TechnicalAnalystRuntimeConfig,
    build_chat_model,
)

TECHNICAL_ANALYST_MAX_TOKENS = 8192
TECHNICAL_ANALYST_TEMPERATURE = 0.1


def build_technical_analyst_model(
    runtime_config: TechnicalAnalystRuntimeConfig,
) -> object:
    """Build the concrete LangChain chat model for one technical analyst run."""
    return build_chat_model(
        runtime_config=runtime_config,
        agent_label="technical-analyst",
        max_tokens=TECHNICAL_ANALYST_MAX_TOKENS,
        temperature=TECHNICAL_ANALYST_TEMPERATURE,
        streaming=False,
    )
