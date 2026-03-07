"""Top-level intent classifier node for conversation orchestrator workflow."""

import logging
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.graphs.workflows.conversation_orchestrator_workflow.state import (
    ConversationOrchestratorWorkflowState,
    TopLevelIntent,
)
from app.infrastructure.llm.factory import get_chat_openai
from app.prompts.system.conversation_orchestrator_intent_classifier import (
    CONVERSATION_ORCHESTRATOR_INTENT_CLASSIFIER_PROMPT,
)

logger = logging.getLogger(__name__)

SUPPORTED_TOP_LEVEL_INTENTS: set[str] = {"chat", "strategic_planning", "unclear"}


class TopLevelIntentClassification(BaseModel):
    """Structured schema for top-level intent classification."""

    intent: TopLevelIntent = Field(
        description=("Top-level routing intent: chat, strategic_planning, or unclear.")
    )


async def intent_classifier_node(
    state: ConversationOrchestratorWorkflowState,
) -> dict[str, TopLevelIntent]:
    """Classify top-level intent for orchestrator routing.

    Fallback behavior is conservative: any ambiguity, failure, or unsupported
    output maps to `unclear`.
    """
    try:
        llm = get_chat_openai(temperature=0.0, streaming=False)
        structured_llm = llm.with_structured_output(TopLevelIntentClassification)

        messages = state.get("messages", [])
        last_user_message = _extract_last_user_message(messages)
        if not last_user_message:
            logger.warning("Top-level intent classification fallback: no user message")
            return {"intent": "unclear"}

        conversation_messages = _build_conversation_messages(messages)
        if not conversation_messages:
            logger.warning(
                "Top-level intent classification fallback: empty conversation messages"
            )
            return {"intent": "unclear"}

        invoke_messages = [
            SystemMessage(content=CONVERSATION_ORCHESTRATOR_INTENT_CLASSIFIER_PROMPT)
        ]
        invoke_messages.extend(conversation_messages)
        invoke_messages.append(
            HumanMessage(
                content=(
                    "Classify the latest user request using the full conversation "
                    "context. Return exactly one intent label."
                )
            )
        )

        result: TopLevelIntentClassification = await structured_llm.ainvoke(
            invoke_messages
        )

        intent_value = result.intent
        if intent_value not in SUPPORTED_TOP_LEVEL_INTENTS:
            logger.warning(
                "Top-level intent classification fallback: unsupported intent '%s'",
                intent_value,
            )
            return {"intent": "unclear"}

        logger.info(
            "Top-level intent classified as %s for message: %s...",
            intent_value,
            last_user_message[:80],
        )
        return {"intent": intent_value}
    except Exception:
        logger.exception("Top-level intent classification failed")
        return {"intent": "unclear"}


def _extract_last_user_message(messages: list) -> Optional[str]:
    """Extract the latest user message content from conversation history."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
        if hasattr(msg, "type") and msg.type == "human":
            return msg.content if hasattr(msg, "content") else str(msg)
    return None


def _build_conversation_messages(messages: list) -> list[HumanMessage | AIMessage]:
    """Map full conversation history to Human/AI messages for classifier input."""
    conversation_messages: list[HumanMessage | AIMessage] = []

    for msg in messages:
        if not hasattr(msg, "content"):
            continue

        content = msg.content
        if content is None:
            continue

        message_type = getattr(msg, "type", "")
        if isinstance(msg, HumanMessage) or message_type == "human":
            conversation_messages.append(HumanMessage(content=str(content)))
        elif isinstance(msg, AIMessage) or message_type == "ai":
            conversation_messages.append(AIMessage(content=str(content)))

    return conversation_messages
