"""Branch-local clarify node for conversation orchestrator workflow."""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.common.event_socket import ChatEvents
from app.infrastructure.llm.factory import get_chat_openai
from app.prompts.system.clarify_node import CLARIFY_NODE_PROMPT
from app.socket_gateway import gateway

logger = logging.getLogger(__name__)


async def clarify_node(state: dict[str, Any]) -> dict[str, str]:
    """Ask the user for clarification when top-level intent is unclear."""
    user_id = state.get("user_id", "")
    conversation_id = state.get("conversation_id", "")
    organization_id = state.get("organization_id")

    try:
        llm = get_chat_openai(temperature=0.7, streaming=True)
        llm_messages = [SystemMessage(content=CLARIFY_NODE_PROMPT)]

        messages = state.get("messages", [])
        for msg in messages:
            if not hasattr(msg, "content"):
                continue

            if isinstance(msg, HumanMessage) or (
                hasattr(msg, "type") and msg.type == "human"
            ):
                llm_messages.append(HumanMessage(content=msg.content))
            elif isinstance(msg, AIMessage) or (
                hasattr(msg, "type") and msg.type == "ai"
            ):
                llm_messages.append(AIMessage(content=msg.content))

        full_content = ""
        async for chunk in llm.astream(llm_messages):
            if chunk.content:
                token = chunk.content
                full_content += token
                await gateway.emit_to_user(
                    user_id=user_id,
                    event=ChatEvents.MESSAGE_TOKEN,
                    data={
                        "conversation_id": conversation_id,
                        "token": token,
                    },
                    organization_id=organization_id,
                )

        logger.info(
            "Orchestrator clarify node generated response: %s...", full_content[:50]
        )
        return {"agent_response": full_content, "error": None}
    except Exception:
        logger.exception("Orchestrator clarify node failed")
        return {
            "agent_response": (
                "I could not clearly understand your request. "
                "Please share a bit more detail so I can help."
            ),
            "error": "orchestrator_clarify_node_failed",
        }
