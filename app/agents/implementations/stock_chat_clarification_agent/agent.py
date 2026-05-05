"""Stock-chat clarification agent runtime implementation."""

from __future__ import annotations

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.stock_chat_clarification_agent.runtime import (
    StockChatRuntimeConfig,
    build_stock_chat_clarification_model,
)
from app.agents.implementations.stock_chat_clarification_agent.validation import (
    StockChatClarificationResult,
)
from app.prompts.system.stock_chat_clarification import (
    get_stock_chat_clarification_system_prompt,
)


def create_stock_chat_clarification_agent(
    runtime_config: StockChatRuntimeConfig | None = None,
) -> CompiledStateGraph:
    """Create the stock-chat clarification agent."""
    llm = build_stock_chat_clarification_model(runtime_config)
    return create_agent(
        model=llm,
        tools=[],
        system_prompt=get_stock_chat_clarification_system_prompt(),
        response_format=StockChatClarificationResult,
    )
