"""Clarify node for asking users to clarify unclear messages.

Emits Socket.IO events directly for real-time token streaming.
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.common.event_socket import ChatEvents
from app.graphs.workflows.chat_workflow.state import ChatWorkflowState
from app.infrastructure.llm.factory import get_chat_openai
from app.prompts.system.clarify_node import CLARIFY_NODE_PROMPT
from app.socket_gateway import gateway

logger = logging.getLogger(__name__)


async def clarify_node(state: ChatWorkflowState) -> dict:
    """Ask user to clarify their unclear message.

    Provides examples of supported queries to help the user
    formulate a clearer question. Streams tokens via Socket.IO.

    Args:
        state: Current workflow state containing messages and context

    Returns:
        dict with "agent_response" key containing the clarification request
    """
    user_id = state.get("user_id", "")
    conversation_id = state.get("conversation_id", "")

    try:
        llm = get_chat_openai(temperature=0.7, streaming=True)

        # Build messages for LLM
        llm_messages = [SystemMessage(content=CLARIFY_NODE_PROMPT)]

        # Add recent conversation for context
        messages = state.get("messages", [])
        for msg in messages[-5:]:  # Last 5 messages
            if hasattr(msg, "content"):
                if isinstance(msg, HumanMessage) or (
                    hasattr(msg, "type") and msg.type == "human"
                ):
                    llm_messages.append(HumanMessage(content=msg.content))
                elif isinstance(msg, AIMessage) or (
                    hasattr(msg, "type") and msg.type == "ai"
                ):
                    llm_messages.append(AIMessage(content=msg.content))

        # Stream response with Socket.IO emit
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
                )

        logger.info("Clarify node generated response: %s...", full_content[:50])
        return {"agent_response": full_content}

    except Exception:
        logger.exception("Clarify node failed")
        # Fallback response in Vietnamese
        return {
            "agent_response": "Tôi chưa hiểu rõ câu hỏi của bạn. Bạn có thể hỏi về:\n"
            "- Tổng doanh thu, số đơn hàng\n"
            "- Top sản phẩm bán chạy\n"
            "- So sánh doanh thu giữa các kỳ\n"
            "- Phân tích theo platform (Shopee, Lazada...)"
        }
