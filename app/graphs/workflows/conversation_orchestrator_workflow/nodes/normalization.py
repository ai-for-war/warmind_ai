"""Normalization utilities for orchestrator route outputs."""

from typing import Any

from app.graphs.workflows.conversation_orchestrator_workflow.state import (
    ConversationOrchestratorWorkflowState,
    OrchestratorOutputEnvelope,
    ResponseType,
    TopLevelIntent,
)

_VALID_INTENTS: set[str] = {"chat", "strategic_planning", "unclear"}
_VALID_RESPONSE_TYPES: set[str] = {
    "chat_message",
    "clarification_request",
    "strategic_package",
}


def normalize_orchestrator_result(
    raw: dict[str, Any],
    *,
    fallback_intent: TopLevelIntent,
    fallback_response_type: ResponseType,
) -> OrchestratorOutputEnvelope:
    """Normalize branch output into a stable orchestrator envelope."""
    raw_intent = raw.get("intent")
    raw_response_type = raw.get("response_type")

    intent: TopLevelIntent = (
        raw_intent if raw_intent in _VALID_INTENTS else fallback_intent
    )
    response_type: ResponseType = (
        raw_response_type
        if raw_response_type in _VALID_RESPONSE_TYPES
        else fallback_response_type
    )

    agent_response = raw.get("agent_response")
    if not isinstance(agent_response, str):
        agent_response = ""

    final_payload = raw.get("final_payload")
    if not isinstance(final_payload, dict):
        final_payload = {}

    tool_calls = raw.get("tool_calls")
    if not isinstance(tool_calls, list):
        tool_calls = []

    error = raw.get("error")
    if error is not None and not isinstance(error, str):
        error = str(error)

    return {
        "intent": intent,
        "response_type": response_type,
        "agent_response": agent_response,
        "final_payload": final_payload,
        "tool_calls": tool_calls,
        "error": error,
    }


async def normalize_output_node(
    state: ConversationOrchestratorWorkflowState,
) -> OrchestratorOutputEnvelope:
    """Normalize current orchestrator state before returning final result."""
    fallback_intent: TopLevelIntent = state.get("intent", "unclear") or "unclear"

    fallback_response_type: ResponseType = "clarification_request"
    if fallback_intent == "chat":
        fallback_response_type = "chat_message"
    elif fallback_intent == "strategic_planning":
        fallback_response_type = "strategic_package"

    return normalize_orchestrator_result(
        raw=state,
        fallback_intent=fallback_intent,
        fallback_response_type=fallback_response_type,
    )
