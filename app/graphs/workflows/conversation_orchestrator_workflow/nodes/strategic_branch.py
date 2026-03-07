"""Strategic planning branch wrapper node for conversation orchestrator workflow."""

import logging
from typing import Any

from app.graphs.registry import get_graph
from app.graphs.workflows.conversation_orchestrator_workflow.nodes.normalization import (
    normalize_orchestrator_result,
)
from app.graphs.workflows.conversation_orchestrator_workflow.state import (
    ConversationOrchestratorWorkflowState,
    OrchestratorOutputEnvelope,
)

logger = logging.getLogger(__name__)

STRATEGIC_WORKFLOW_NAME = "strategic_planning_workflow"


async def strategic_branch_node(
    state: ConversationOrchestratorWorkflowState,
) -> OrchestratorOutputEnvelope:
    """Invoke strategic planning path and map output to orchestrator envelope."""
    try:
        strategic_graph = get_graph(STRATEGIC_WORKFLOW_NAME)
        strategic_result: dict[str, Any] = await strategic_graph.ainvoke(
            {
                "messages": state.get("messages", []),
                "user_id": state.get("user_id", ""),
                "conversation_id": state.get("conversation_id", ""),
                "tool_calls": state.get("tool_calls", []),
            }
        )
    except KeyError:
        logger.warning(
            "Strategic workflow '%s' is not registered", STRATEGIC_WORKFLOW_NAME
        )
        strategic_result = {
            "agent_response": (
                "Strategic planning workflow is not available yet. "
                "Please provide more details or try again later."
            ),
            "final_payload": {},
            "tool_calls": [],
            "error": "strategic_planning_workflow_not_registered",
            "response_type": "clarification_request",
        }
    except Exception as exc:
        logger.exception("Strategic branch wrapper failed")
        strategic_result = {
            "agent_response": "",
            "final_payload": {},
            "tool_calls": [],
            "error": str(exc),
        }

    return normalize_orchestrator_result(
        raw={
            "intent": "strategic_planning",
            "response_type": strategic_result.get("response_type", "strategic_package"),
            "agent_response": strategic_result.get("agent_response"),
            "final_payload": strategic_result.get("final_payload", {}),
            "tool_calls": strategic_result.get("tool_calls", []),
            "error": strategic_result.get("error"),
        },
        fallback_intent="strategic_planning",
        fallback_response_type="strategic_package",
    )
