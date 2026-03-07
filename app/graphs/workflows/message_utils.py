"""Shared workflow message utilities."""

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage


def build_agent_messages(messages: list[Any]) -> list[Any]:
    """Map full conversation history into Human/AI messages for agent input."""
    agent_messages: list[Any] = []

    for msg in messages:
        if not hasattr(msg, "content"):
            continue

        content = msg.content
        if content is None:
            continue

        if isinstance(msg, HumanMessage) or (
            hasattr(msg, "type") and msg.type == "human"
        ):
            agent_messages.append(HumanMessage(content=str(content)))
        elif isinstance(msg, AIMessage) or (hasattr(msg, "type") and msg.type == "ai"):
            agent_messages.append(AIMessage(content=str(content)))

    return agent_messages
