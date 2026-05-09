"""Dedicated fundamental analyst agent runtime implementation."""

from __future__ import annotations

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.fundamental_analyst.middleware import (
    build_fundamental_analyst_middleware,
)
from app.agents.implementations.fundamental_analyst.runtime import (
    FundamentalAnalystRuntimeConfig,
    build_fundamental_analyst_model,
)
from app.agents.implementations.fundamental_analyst.tools.builder import (
    get_fundamental_analyst_tool_surface,
)
from app.agents.implementations.fundamental_analyst.validation import (
    FundamentalAnalystOutput,
)
from app.prompts.system.fundamental_analyst import (
    get_fundamental_analyst_system_prompt,
)


def create_fundamental_analyst_agent(
    runtime_config: FundamentalAnalystRuntimeConfig,
) -> CompiledStateGraph:
    """Create the dedicated fundamental analyst runtime with financial tools."""
    llm = build_fundamental_analyst_model(runtime_config)
    tool_surface = get_fundamental_analyst_tool_surface()

    return create_agent(
        model=llm,
        tools=list(tool_surface.tools),
        system_prompt=get_fundamental_analyst_system_prompt(),
        middleware=build_fundamental_analyst_middleware(llm),
        response_format=FundamentalAnalystOutput,
    )
