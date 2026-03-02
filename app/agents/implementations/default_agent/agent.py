"""Default agent implementation using LangGraph ReAct pattern."""

from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.agents.implementations.default_agent.tools import calculator
from app.infrastructure.llm.factory import get_chat_openai
from app.prompts.system.default_agent import DEFAULT_AGENT_SYSTEM_PROMPT


def create_default_agent() -> CompiledStateGraph:
    """Create a ReAct agent with calculator tool.

    Returns:
        A compiled LangGraph agent ready for streaming execution.
    """
    llm = get_chat_openai()
    tools = [calculator]

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=DEFAULT_AGENT_SYSTEM_PROMPT,
    )

    return agent
