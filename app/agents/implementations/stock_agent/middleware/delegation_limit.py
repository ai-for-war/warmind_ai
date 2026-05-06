"""Delegation guardrail middleware for the stock-agent runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.agents.implementations.stock_agent.middleware.constants import (
    DELEGATION_TOOL_NAME,
)
from app.agents.implementations.stock_agent.state import StockAgentState
from app.config.settings import get_settings


class StockAgentDelegationLimitMiddleware(AgentMiddleware[StockAgentState, None, Any]):
    """Reject over-limit parallel delegation batches from a single model turn."""

    state_schema = StockAgentState
    tools: Sequence[BaseTool] = ()

    def after_model(
        self,
        state: StockAgentState,
        runtime,
    ) -> dict[str, Any] | None:
        """Return tool errors when one model turn exceeds the delegation fan-out limit."""
        messages = state["messages"]
        if not messages:
            return None

        last_ai_msg = next(
            (msg for msg in reversed(messages) if isinstance(msg, AIMessage)),
            None,
        )
        if not last_ai_msg or not last_ai_msg.tool_calls:
            return None

        delegate_calls = [
            tool_call
            for tool_call in last_ai_msg.tool_calls
            if tool_call["name"] == DELEGATION_TOOL_NAME
        ]
        max_parallel_subagents = get_settings().STOCK_AGENT_MAX_PARALLEL_SUBAGENTS
        if len(delegate_calls) <= max_parallel_subagents:
            return None

        error_messages = [
            ToolMessage(
                content=(
                    f"Error: `{DELEGATION_TOOL_NAME}` was called {len(delegate_calls)} times in "
                    f"parallel, but the maximum allowed per model invocation is "
                    f"{max_parallel_subagents}. Limit each turn to at most "
                    f"{max_parallel_subagents} delegated subagents."
                ),
                tool_call_id=str(tool_call["id"]),
                status="error",
            )
            for tool_call in delegate_calls
        ]
        return {"messages": error_messages}

    async def aafter_model(
        self,
        state: StockAgentState,
        runtime,
    ) -> dict[str, Any] | None:
        """Async wrapper for the delegation batch limit guardrail."""
        return self.after_model(state, runtime)
