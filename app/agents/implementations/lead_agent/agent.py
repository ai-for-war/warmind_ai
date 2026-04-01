"""Lead-agent runtime implementation built on LangChain's create_agent."""

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.lead_agent.middleware import LEAD_AGENT_MIDDLEWARE
from app.agents.implementations.lead_agent.runtime import (
    LeadAgentRuntimeConfig,
    build_lead_agent_model,
)
from app.agents.implementations.lead_agent.state import LeadAgentState
from app.agents.implementations.lead_agent.tool_catalog import get_lead_agent_tools
from app.infrastructure.langgraph.checkpointer import get_langgraph_checkpointer
from app.prompts.system.lead_agent import get_lead_agent_system_prompt


def create_lead_agent(
    runtime_config: LeadAgentRuntimeConfig | None = None,
) -> CompiledStateGraph:
    """Create a skill-aware lead-agent runtime for one resolved model config."""
    llm = build_lead_agent_model(runtime_config)

    return create_agent(
        model=llm,
        tools=get_lead_agent_tools(),
        system_prompt=get_lead_agent_system_prompt(),
        middleware=LEAD_AGENT_MIDDLEWARE,
        state_schema=LeadAgentState,
        checkpointer=get_langgraph_checkpointer(),
    )
