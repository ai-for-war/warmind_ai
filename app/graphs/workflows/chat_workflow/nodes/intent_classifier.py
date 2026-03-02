"""Intent classifier node for routing user messages.

Uses LangChain's with_structured_output for guaranteed valid responses.
Best practices:
- Pydantic schema ensures output is always valid
- Temperature 0 for deterministic classification
- Few-shot examples in prompt for accuracy
- Conversation context for better understanding
"""

import logging
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.graphs.workflows.chat_workflow.state import ChatWorkflowState
from app.infrastructure.llm.factory import get_chat_openai
from app.prompts.system.intent_classifier import INTENT_CLASSIFIER_PROMPT

logger = logging.getLogger(__name__)

IntentType = Literal["data_query", "chat", "unclear"]
ConfidenceLevel = Literal["high", "medium", "low"]


class IntentClassification(BaseModel):
    """Structured output schema for intent classification.

    Using Pydantic with Literal types ensures the LLM can only
    return valid intent values, eliminating parsing errors.
    """

    intent: IntentType = Field(
        description="The classified intent: data_query for data/analytics questions, "
        "chat for greetings/general conversation, unclear for ambiguous messages"
    )


async def intent_classifier_node(state: ChatWorkflowState) -> dict:
    """Classify user intent using LLM with structured output.

    Uses with_structured_output to guarantee the response is always
    one of the valid intent types, eliminating parsing errors.

    Args:
        state: Current workflow state containing messages and context

    Returns:
        dict with "intent" key containing one of: "data_query", "chat", "unclear"
    """
    try:
        # Use temperature 0 for deterministic classification
        llm = get_chat_openai(temperature=0.0, streaming=False)

        # Bind structured output schema to LLM
        structured_llm = llm.with_structured_output(IntentClassification)

        # Get the last user message
        messages = state.get("messages", [])
        last_user_message = _extract_last_user_message(messages)

        if not last_user_message:
            logger.warning("No user message found in state")
            return {"intent": "unclear"}

        # Build conversation context for better classification
        context_str = _build_conversation_context(messages)

        # Create classification prompt with context
        classification_prompt = _build_classification_prompt(
            last_user_message, context_str
        )

        # Invoke LLM with structured output
        result: IntentClassification = await structured_llm.ainvoke(
            [
                SystemMessage(content=INTENT_CLASSIFIER_PROMPT),
                HumanMessage(content=classification_prompt),
            ]
        )

        intent = result.intent

        logger.info(
            "Classified intent: %s for message: %s...", intent, last_user_message[:50]
        )

        return {"intent": intent}

    except Exception:
        logger.exception("Intent classification failed")
        return {"intent": "unclear"}


def _extract_last_user_message(messages: list) -> Optional[str]:
    """Extract the last user message from conversation history.

    Args:
        messages: List of conversation messages

    Returns:
        Content of the last user message, or None if not found
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
        if hasattr(msg, "type") and msg.type == "human":
            return msg.content if hasattr(msg, "content") else str(msg)
    return None


def _build_conversation_context(messages: list, max_messages: int = 5) -> str:
    """Build conversation context string from recent messages.

    Args:
        messages: List of conversation messages
        max_messages: Maximum number of recent messages to include

    Returns:
        Formatted string of recent conversation history
    """
    context_parts = []
    for msg in messages[-max_messages:]:
        if hasattr(msg, "content"):
            role = "user" if getattr(msg, "type", "") == "human" else "assistant"
            context_parts.append(f"{role}: {msg.content}")

    return "\n".join(context_parts) if context_parts else ""


def _build_classification_prompt(user_message: str, context: str) -> str:
    """Build the classification prompt with user message and context.

    Args:
        user_message: The message to classify
        context: Recent conversation context

    Returns:
        Formatted prompt for classification
    """
    if context:
        return f"""<conversation_history>
{context}
</conversation_history>

<message_to_classify>
{user_message}
</message_to_classify>

Classify the message above based on its content and conversation context."""

    return f"""<message_to_classify>
{user_message}
</message_to_classify>

Classify the message above."""
