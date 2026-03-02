"""Chat workflow state definition."""

from typing import Annotated, Optional, TypedDict

from langgraph.graph.message import add_messages


class ToolCallRecord(TypedDict):
    """Record of a tool call made during workflow execution.

    Attributes:
        tool_name: Name of the tool that was called
        tool_call_id: Unique identifier for the tool call
        arguments: Arguments passed to the tool
        result: Result returned by the tool (if successful)
        error: Error message (if tool call failed)
    """

    tool_name: str
    tool_call_id: str
    arguments: dict
    result: Optional[str]
    error: Optional[str]


class ChatWorkflowState(TypedDict):
    """State for the chat workflow.

    Attributes:
        messages: Conversation history with automatic message merging
        user_id: ID of the user making the request
        conversation_id: ID of the current conversation
        user_connections: List of user's sheet connections with schemas
        intent: Classified intent ("data_query", "chat", "unclear")
        agent_response: Response from the agent/node
        tool_calls: History of tool calls for streaming
        error: Error message if workflow fails
    """

    messages: Annotated[list, add_messages]
    user_id: str
    conversation_id: str
    user_connections: list[dict]
    intent: Optional[str]
    agent_response: Optional[str]
    tool_calls: list[ToolCallRecord]
    error: Optional[str]
