"""Lead-agent runtime implementation built on LangChain's create_agent."""

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.lead_agent.middleware import LEAD_AGENT_MIDDLEWARE
from app.agents.implementations.lead_agent.state import LeadAgentState
from app.agents.implementations.lead_agent.tools import LEAD_AGENT_TOOLS
from app.infrastructure.langgraph.checkpointer import get_langgraph_checkpointer
from app.infrastructure.llm.factory import get_chat_azure_openai_legacy


def create_lead_agent() -> CompiledStateGraph:
    """Create the V1 lead-agent runtime with explicit extension seams."""
    llm = get_chat_azure_openai_legacy()

    return create_agent(
        model=llm,
        tools=LEAD_AGENT_TOOLS,
        middleware=LEAD_AGENT_MIDDLEWARE,
        state_schema=LeadAgentState,
        checkpointer=get_langgraph_checkpointer(),
    )
