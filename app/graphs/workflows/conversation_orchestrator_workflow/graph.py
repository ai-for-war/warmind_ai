"""Conversation orchestrator routing primitives.

Graph assembly is implemented in follow-up tasks for branch node wiring.
"""

import logging
from typing import Literal

from app.graphs.workflows.conversation_orchestrator_workflow.state import (
    ConversationOrchestratorWorkflowState,
)

logger = logging.getLogger(__name__)

RouteDestination = Literal["chat_branch", "strategic_branch", "clarify_branch"]


def route_by_top_level_intent(
    state: ConversationOrchestratorWorkflowState,
) -> RouteDestination:
    """Map top-level intent to orchestrator handling path.

    Conservative fallback behavior:
    - Unsupported/invalid intents route to clarification path.
    - Missing intents route to clarification path.
    """
    intent = state.get("intent", "unclear")

    if intent == "chat":
        logger.info("Routing to chat branch")
        return "chat_branch"
    if intent == "strategic_planning":
        logger.info("Routing to strategic branch")
        return "strategic_branch"

    logger.info("Routing to clarification branch (intent: %s)", intent)
    return "clarify_branch"
