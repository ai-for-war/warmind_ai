"""Chat branch wrapper node for conversation orchestrator workflow."""

import logging

from app.graphs.workflows.chat_workflow.nodes.chat_node import chat_node
from app.graphs.workflows.conversation_orchestrator_workflow.nodes.normalization import (
    normalize_orchestrator_result,
)
from app.graphs.workflows.conversation_orchestrator_workflow.state import (
    ConversationOrchestratorWorkflowState,
    OrchestratorOutputEnvelope,
)

logger = logging.getLogger(__name__)


async def chat_branch_node(
    state: ConversationOrchestratorWorkflowState,
) -> OrchestratorOutputEnvelope:
    """Invoke chat handling path and map output to orchestrator envelope."""
    try:
        chat_result = await chat_node(
            {
                "messages": state.get("messages", []),
                "user_id": state.get("user_id", ""),
                "conversation_id": state.get("conversation_id", ""),
                "user_connections": [],
                "intent": "chat",
                "agent_response": None,
                "tool_calls": state.get("tool_calls", []),
                "error": None,
            }
        )
    except Exception as exc:
        logger.exception("Chat branch wrapper failed")
        chat_result = {"agent_response": "", "tool_calls": [], "error": str(exc)}

    return normalize_orchestrator_result(
        raw={
            "intent": "chat",
            "response_type": "chat_message",
            "agent_response": chat_result.get("agent_response"),
            "final_payload": chat_result.get("final_payload", {}),
            "tool_calls": chat_result.get("tool_calls", []),
            "error": chat_result.get("error"),
        },
        fallback_intent="chat",
        fallback_response_type="chat_message",
    )
