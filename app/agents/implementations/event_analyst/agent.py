"""Dedicated event analyst agent runtime implementation."""

from __future__ import annotations

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.event_analyst.middleware import (
    build_event_analyst_middleware,
)
from app.agents.implementations.event_analyst.runtime import (
    EventAnalystRuntimeConfig,
    build_event_analyst_model,
)
from app.agents.implementations.event_analyst.tools import (
    get_event_analyst_tool_surface,
)
from app.agents.implementations.event_analyst.validation import (
    EventAnalystOutput,
)
from app.prompts.system.event_analyst import (
    get_event_analyst_system_prompt,
)


def create_event_analyst_agent(
    runtime_config: EventAnalystRuntimeConfig,
) -> CompiledStateGraph:
    """Create the dedicated event analyst runtime with normalized web tools."""
    llm = build_event_analyst_model(runtime_config)
    tool_surface = get_event_analyst_tool_surface()

    return create_agent(
        model=llm,
        tools=list(tool_surface.tools),
        system_prompt=get_event_analyst_system_prompt(),
        middleware=build_event_analyst_middleware(llm),
        response_format=EventAnalystOutput,
    )
