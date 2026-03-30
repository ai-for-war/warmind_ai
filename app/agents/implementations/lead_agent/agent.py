"""Lead-agent runtime implementation built on LangChain's create_agent."""

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.lead_agent.middleware import LEAD_AGENT_MIDDLEWARE
from app.agents.implementations.lead_agent.state import LeadAgentState
from app.agents.implementations.lead_agent.tool_catalog import get_lead_agent_tools
from app.infrastructure.langgraph.checkpointer import get_langgraph_checkpointer
from app.infrastructure.llm.factory import get_chat_azure_openai_legacy
from app.prompts.system.lead_agent import get_lead_agent_system_prompt


def create_lead_agent() -> CompiledStateGraph:
    """Create the shared skill-aware lead-agent runtime."""
    llm = get_chat_azure_openai_legacy(
        max_tokens=16384,
    )

    return create_agent(
        model=llm,
        tools=get_lead_agent_tools(),
        system_prompt=get_lead_agent_system_prompt(),
        middleware=LEAD_AGENT_MIDDLEWARE,
        state_schema=LeadAgentState,
        checkpointer=get_langgraph_checkpointer(),
    )
