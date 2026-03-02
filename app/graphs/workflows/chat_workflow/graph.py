"""Chat workflow graph definition.

Implements the main LangGraph workflow for AI chat with intent-based routing.
Routes user messages to appropriate handlers based on classified intent:
- data_query -> Data Agent Node
- chat -> Chat Node
- unclear -> Clarify Node
"""

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graphs.workflows.chat_workflow.nodes.chat_node import chat_node
from app.graphs.workflows.chat_workflow.nodes.clarify_node import clarify_node
from app.graphs.workflows.chat_workflow.nodes.data_agent_node import data_agent_node
from app.graphs.workflows.chat_workflow.nodes.intent_classifier import (
    intent_classifier_node,
)
from app.graphs.workflows.chat_workflow.state import ChatWorkflowState

logger = logging.getLogger(__name__)

# Type alias for routing destinations
RouteDestination = Literal["chat_node", "data_agent_node", "clarify_node"]


def route_by_intent(state: ChatWorkflowState) -> RouteDestination:
    """Route to appropriate node based on classified intent.

    Args:
        state: Current workflow state containing the classified intent

    Returns:
        Name of the node to route to:
        - "data_agent_node" for data_query intent
        - "chat_node" for chat intent
        - "clarify_node" for unclear intent (default)
    """
    intent = state.get("intent", "unclear")

    if intent == "data_query":
        logger.info("Routing to data_agent_node")
        return "data_agent_node"
    if intent == "chat":
        logger.info("Routing to chat_node")
        return "chat_node"

    logger.info("Routing to clarify_node (intent: %s)", intent)
    return "clarify_node"


class ChatWorkflow:
    """LangGraph workflow for AI chat with intent-based routing.

    The workflow follows this structure:
    1. START -> intent_classifier: Classify user intent
    2. intent_classifier -> (conditional routing based on intent):
       - data_query -> data_agent_node
       - chat -> chat_node
       - unclear -> clarify_node
    3. All handler nodes -> END

    Attributes:
        graph: The StateGraph instance
        user_connections: List of user's sheet connections with schemas
    """

    def __init__(self, user_connections: list[dict] | None = None):
        """Initialize the chat workflow.

        Args:
            user_connections: Optional list of user's sheet connections.
                             Passed to state for data agent to use.
        """
        self.user_connections = user_connections or []
        self.graph = StateGraph(ChatWorkflowState)
        self._build_graph()

    def _build_graph(self) -> None:
        """Build the workflow graph with nodes and edges."""
        # Add all nodes
        self.graph.add_node("intent_classifier", intent_classifier_node)
        self.graph.add_node("chat_node", chat_node)
        self.graph.add_node("data_agent_node", data_agent_node)
        self.graph.add_node("clarify_node", clarify_node)

        # Add edge from START to intent_classifier
        self.graph.add_edge(START, "intent_classifier")

        # Add conditional edges from intent_classifier to handler nodes
        self.graph.add_conditional_edges(
            "intent_classifier",
            route_by_intent,
            {
                "chat_node": "chat_node",
                "data_agent_node": "data_agent_node",
                "clarify_node": "clarify_node",
            },
        )

        # Add edges from handler nodes to END
        self.graph.add_edge("chat_node", END)
        self.graph.add_edge("data_agent_node", END)
        self.graph.add_edge("clarify_node", END)

    def compile(self) -> CompiledStateGraph:
        """Compile the workflow graph.

        Returns:
            Compiled StateGraph ready for execution
        """
        return self.graph.compile()


def create_chat_workflow(
    user_connections: list[dict] | None = None,
) -> CompiledStateGraph:
    """Factory function to create a compiled chat workflow.

    This is the main entry point for creating chat workflow instances.
    Can be registered with the graph registry.

    Args:
        user_connections: Optional list of user's sheet connections with schemas

    Returns:
        Compiled LangGraph StateGraph ready for execution

    Example:
        >>> workflow = create_chat_workflow(user_connections)
        >>> result = await workflow.ainvoke({
        ...     "messages": [HumanMessage(content="Hello")],
        ...     "user_id": "user123",
        ...     "conversation_id": "conv456",
        ...     "user_connections": user_connections,
        ... })
    """
    workflow = ChatWorkflow(user_connections)
    return workflow.compile()
