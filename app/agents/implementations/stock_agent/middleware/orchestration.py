"""Orchestration prompt middleware for the stock-agent runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from app.agents.implementations.stock_agent.middleware.shared import (
    as_state_dict,
    merge_system_prompt,
    normalize_bool,
    normalize_non_negative_int,
)
from app.agents.implementations.stock_agent.state import StockAgentState
from app.prompts.system.stock_agent import (
    get_stock_agent_orchestration_system_prompt,
    get_stock_agent_worker_system_prompt,
)


class StockAgentOrchestrationPromptMiddleware(
    AgentMiddleware[StockAgentState, None, Any]
):
    """Inject orchestration or worker-specific behavior prompts per turn."""

    state_schema = StockAgentState
    tools: Sequence[BaseTool] = ()

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler,
    ) -> ModelResponse[Any]:
        state = as_state_dict(request.state)
        prompt_update = _resolve_orchestration_prompt_update(
            state,
            existing_prompt=request.system_prompt,
        )
        if prompt_update is None:
            return await handler(request)

        updated_request = request.override(
            system_message=SystemMessage(content=prompt_update)
        )
        return await handler(updated_request)


def _resolve_orchestration_prompt_update(
    state: dict[str, Any],
    *,
    existing_prompt: str | None,
) -> str | None:
    """Return the full system prompt content appropriate for the current run."""
    delegation_depth = normalize_non_negative_int(state.get("delegation_depth"))
    if delegation_depth > 0:
        return get_stock_agent_worker_system_prompt()

    if normalize_bool(state.get("subagent_enabled")):
        return merge_system_prompt(
            existing_prompt,
            [get_stock_agent_orchestration_system_prompt()],
        )

    return None
