"""Stock-agent runtime implementation built on LangChain's create_agent."""

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.stock_agent.middleware.builder import (
    build_stock_agent_middleware,
)
from app.agents.implementations.stock_agent.runtime import (
    StockAgentRuntimeConfig,
    build_stock_agent_model,
)
from app.agents.implementations.stock_agent.state import StockAgentState
from app.agents.implementations.stock_agent.tool_catalog import get_stock_agent_tools
from app.infrastructure.langgraph.checkpointer import get_langgraph_checkpointer
from app.prompts.system.stock_agent import get_stock_agent_system_prompt


def create_stock_agent(
    runtime_config: StockAgentRuntimeConfig | None = None,
    *,
    subagent_enabled: bool = False,
) -> CompiledStateGraph:
    """Create a skill-aware stock-agent runtime for one resolved model config."""
    llm = build_stock_agent_model(runtime_config)

    return create_agent(
        model=llm,
        tools=get_stock_agent_tools(),
        system_prompt=get_stock_agent_system_prompt(
            subagent_enabled=subagent_enabled
        ),
        middleware=build_stock_agent_middleware(llm),
        state_schema=StockAgentState,
        checkpointer=get_langgraph_checkpointer(),
    )
