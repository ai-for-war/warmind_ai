"""Conversation orchestrator workflow graph definition."""

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graphs.workflows.conversation_orchestrator_workflow.nodes import (
    chat_node,
    clarify_node,
    intent_classifier_node,
    normalize_output_node,
    strategic_branch_node,
)
from app.graphs.workflows.conversation_orchestrator_workflow.state import (
    ConversationOrchestratorWorkflowState,
)

logger = logging.getLogger(__name__)

RouteDestination = Literal["chat_node", "strategic_branch", "clarify_node"]


def route_by_top_level_intent(
    state: ConversationOrchestratorWorkflowState,
) -> RouteDestination:
    """Map top-level intent to orchestrator handling path.

    Conservative fallback behavior:
    - Unsupported/invalid intents route to clarification path.
    - Missing intents route to clarification path.
    """
    intent = state.get("intent", "unclear")

    if intent == "normal_chat":
        logger.info("Routing to normal chat node")
        return "chat_node"
    if intent == "strategic_planning":
        logger.info("Routing to strategic branch")
        return "strategic_branch"

    logger.info("Routing to clarification branch (intent: %s)", intent)
    return "clarify_node"


class ConversationOrchestratorWorkflow:
    """Top-level orchestrator workflow with explicit conditional routing."""

    def __init__(self) -> None:
        self.graph = StateGraph(ConversationOrchestratorWorkflowState)
        self._build_graph()

    def _build_graph(self) -> None:
        """Build orchestrator graph with routing and normalization."""
        self.graph.add_node("intent_classifier", intent_classifier_node)
        self.graph.add_node("chat_node", chat_node)
        self.graph.add_node("strategic_branch", strategic_branch_node)
        self.graph.add_node("clarify_node", clarify_node)
        self.graph.add_node("normalize_output", normalize_output_node)

        self.graph.add_edge(START, "intent_classifier")

        self.graph.add_conditional_edges(
            "intent_classifier",
            route_by_top_level_intent,
            {
                "chat_node": "chat_node",
                "strategic_branch": "strategic_branch",
                "clarify_node": "clarify_node",
            },
        )

        self.graph.add_edge("chat_node", "normalize_output")
        self.graph.add_edge("strategic_branch", "normalize_output")
        self.graph.add_edge("clarify_node", "normalize_output")
        self.graph.add_edge("normalize_output", END)

    def compile(self) -> CompiledStateGraph:
        """Compile orchestrator workflow graph."""
        return self.graph.compile()


def create_conversation_orchestrator_workflow() -> CompiledStateGraph:
    """Factory function to create the compiled orchestrator workflow."""
    workflow = ConversationOrchestratorWorkflow()
    return workflow.compile()
