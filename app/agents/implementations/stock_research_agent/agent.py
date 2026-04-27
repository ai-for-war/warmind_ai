"""Dedicated stock-research agent runtime implementation."""

from __future__ import annotations

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.stock_research_agent.middleware import (
    build_stock_research_middleware,
)
from app.agents.implementations.stock_research_agent.runtime import (
    StockResearchAgentRuntimeConfig,
    build_stock_research_model,
)
from app.agents.implementations.stock_research_agent.tools import (
    get_stock_research_tool_surface,
)
from app.agents.implementations.stock_research_agent.validation import (
    StockResearchAgentOutput,
)
from app.prompts.system.stock_research_agent import (
    get_stock_research_agent_system_prompt,
)


def create_stock_research_agent(
    runtime_config: StockResearchAgentRuntimeConfig | None = None,
) -> CompiledStateGraph:
    """Create the dedicated stock-research runtime with normalized web tools."""
    llm = build_stock_research_model(runtime_config)
    tool_surface = get_stock_research_tool_surface()

    return create_agent(
        model=llm,
        tools=list(tool_surface.tools),
        system_prompt=get_stock_research_agent_system_prompt(),
        middleware=build_stock_research_middleware(llm),
        response_format=StockResearchAgentOutput,
    )
