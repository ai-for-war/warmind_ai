"""Dedicated technical analyst agent runtime implementation."""

from __future__ import annotations

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.technical_analyst.middleware import (
    build_technical_analyst_middleware,
)
from app.agents.implementations.technical_analyst.runtime import (
    TechnicalAnalystRuntimeConfig,
    build_technical_analyst_model,
)
from app.agents.implementations.technical_analyst.tools.builder import (
    get_technical_analyst_tool_surface,
)
from app.agents.implementations.technical_analyst.validation import (
    TechnicalAnalystOutput,
)
from app.prompts.system.technical_analyst import (
    get_technical_analyst_system_prompt,
)


def create_technical_analyst_agent(
    runtime_config: TechnicalAnalystRuntimeConfig,
) -> CompiledStateGraph:
    """Create the dedicated technical analyst runtime with deterministic tools."""
    llm = build_technical_analyst_model(runtime_config)
    tool_surface = get_technical_analyst_tool_surface()

    return create_agent(
        model=llm,
        tools=list(tool_surface.tools),
        system_prompt=get_technical_analyst_system_prompt(),
        middleware=build_technical_analyst_middleware(llm),
        response_format=TechnicalAnalystOutput,
    )
