"""State and contracts for conversation orchestrator workflow."""

from typing import Annotated, Any, Literal, Optional, TypedDict

from langgraph.graph.message import add_messages

TopLevelIntent = Literal["chat", "strategic_planning", "unclear"]
ResponseType = Literal["chat_message", "clarification_request", "strategic_package"]


class ToolCallRecord(TypedDict):
    """Normalized record of a tool call across orchestrator branches."""

    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    result: Optional[str]
    error: Optional[str]


class OrchestratorOutputEnvelope(TypedDict):
    """Normalized orchestrator output contract returned by all routes."""

    intent: TopLevelIntent
    response_type: ResponseType
    agent_response: str
    final_payload: dict[str, Any]
    tool_calls: list[ToolCallRecord]
    error: Optional[str]


class ConversationOrchestratorWorkflowState(TypedDict):
    """Parent workflow state limited to shared orchestrator fields."""

    messages: Annotated[list, add_messages]
    user_id: str
    conversation_id: str
    intent: Optional[TopLevelIntent]
    response_type: Optional[ResponseType]
    agent_response: Optional[str]
    final_payload: dict[str, Any]
    tool_calls: list[ToolCallRecord]
    error: Optional[str]
