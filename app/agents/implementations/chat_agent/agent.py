"""Chat Agent implementation using LangGraph ReAct pattern.

This agent handles general conversation with web search capability.
It uses MCP tools to search the web and fetch content when users
ask questions requiring current or external information.

Requirements: 4.1, 4.2 (Chat Agent with MCP tools)
"""

import logging

from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.infrastructure.llm.factory import get_chat_openai
from app.infrastructure.mcp.manager import get_mcp_tools_manager
from app.prompts.system.chat_agent import CHAT_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def create_chat_agent() -> CompiledStateGraph:
    """Create a ReAct agent with web search capability.

    This agent is designed for general conversation and can search
    the web when users ask questions requiring current information,
    news, or external data.

    Returns:
        A compiled LangGraph agent ready for streaming execution.

    Requirements:
        - 4.1: Chat_Node upgraded to Chat_Agent with tool calling
        - 4.2: Chat_Agent includes MCP web search tools
    """
    # Create LLM instance with higher temperature for conversational responses
    llm = get_chat_openai(
        temperature=0.7,  # Higher temperature for more natural conversation
        streaming=True,
    )

    # Get MCP tools (web search, fetch content)
    mcp_manager = get_mcp_tools_manager()
    # DuckDuckGo MCP provides: "search" and "fetch" tools
    mcp_tools = mcp_manager.get_tools(tool_names=["search", "fetch_content"])

    if mcp_tools:
        logger.info(
            "Chat agent initialized with %d MCP tools: %s",
            len(mcp_tools),
            [t.name for t in mcp_tools],
        )
    else:
        logger.warning("No MCP tools available for chat agent")

    # Create ReAct agent with MCP tools and system prompt
    agent = create_react_agent(
        model=llm,
        tools=mcp_tools,
        prompt=CHAT_AGENT_SYSTEM_PROMPT,
    )

    return agent
