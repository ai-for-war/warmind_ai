"""Runtime helpers for fundamental analyst execution."""

from __future__ import annotations

from app.agents.runtime import (
    AgentRuntimeConfig as FundamentalAnalystRuntimeConfig,
    build_chat_model,
)

FUNDAMENTAL_ANALYST_MAX_TOKENS = 8192
FUNDAMENTAL_ANALYST_TEMPERATURE = 0.1


def build_fundamental_analyst_model(
    runtime_config: FundamentalAnalystRuntimeConfig,
) -> object:
    """Build the concrete LangChain chat model for one fundamental analyst run."""
    return build_chat_model(
        runtime_config=runtime_config,
        agent_label="fundamental-analyst",
        max_tokens=FUNDAMENTAL_ANALYST_MAX_TOKENS,
        temperature=FUNDAMENTAL_ANALYST_TEMPERATURE,
        streaming=False,
    )
