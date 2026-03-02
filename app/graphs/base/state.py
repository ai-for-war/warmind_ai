"""Shared state definitions for LangGraph workflows."""

from typing import Annotated, Optional, TypedDict
from langgraph.graph.message import add_messages


class BaseWorkflowState(TypedDict):
    """Base state shared across all workflows.

    Attributes:
        messages: Conversation history with automatic message merging
        user_id: ID of the user making the request
        conversation_id: ID of the current conversation
        error: Error message if workflow fails
    """

    messages: Annotated[list, add_messages]
    user_id: str
    conversation_id: str
    error: Optional[str]
