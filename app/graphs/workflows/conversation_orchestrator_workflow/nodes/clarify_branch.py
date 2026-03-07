"""Clarification branch wrapper node for conversation orchestrator workflow."""

import logging

from app.graphs.workflows.chat_workflow.nodes.clarify_node import clarify_node
from app.graphs.workflows.conversation_orchestrator_workflow.nodes.normalization import (
    normalize_orchestrator_result,
)
from app.graphs.workflows.conversation_orchestrator_workflow.state import (
    ConversationOrchestratorWorkflowState,
    OrchestratorOutputEnvelope,
)

logger = logging.getLogger(__name__)


async def clarify_branch_node(
    state: ConversationOrchestratorWorkflowState,
) -> OrchestratorOutputEnvelope:
    """Reuse clarification handling path and normalize its output."""
    try:
        clarify_result = await clarify_node(
            {
                "messages": state.get("messages", []),
                "user_id": state.get("user_id", ""),
                "conversation_id": state.get("conversation_id", ""),
                "user_connections": [],
                "intent": "unclear",
                "agent_response": None,
                "tool_calls": state.get("tool_calls", []),
                "error": None,
            }
        )
    except Exception as exc:
        logger.exception("Clarify branch wrapper failed")
        clarify_result = {"agent_response": "", "tool_calls": [], "error": str(exc)}

    return normalize_orchestrator_result(
        raw={
            "intent": "unclear",
            "response_type": "clarification_request",
            "agent_response": clarify_result.get("agent_response"),
            "final_payload": clarify_result.get("final_payload", {}),
            "tool_calls": clarify_result.get("tool_calls", []),
            "error": clarify_result.get("error"),
        },
        fallback_intent="unclear",
        fallback_response_type="clarification_request",
    )
