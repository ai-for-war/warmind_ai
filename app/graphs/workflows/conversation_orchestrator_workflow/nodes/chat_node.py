"""Branch-local chat node for conversation orchestrator workflow."""

import logging
from typing import Any

from langchain_core.messages import AIMessage

from app.agents.implementations.chat_agent.agent import create_chat_agent
from app.common.event_socket import ChatEvents
from app.graphs.workflows.message_utils import build_agent_messages
from app.graphs.workflows.conversation_orchestrator_workflow.state import ToolCallRecord
from app.socket_gateway import gateway

logger = logging.getLogger(__name__)


async def chat_node(state: dict[str, Any]) -> dict[str, Any]:
    """Handle normal chat requests for orchestrator normal_chat branch."""
    user_id = state.get("user_id", "")
    conversation_id = state.get("conversation_id", "")
    tool_calls: list[ToolCallRecord] = []

    try:
        agent = create_chat_agent()
        messages = state.get("messages", [])
        agent_messages = build_agent_messages(messages)

        agent_response = await _stream_chat_agent_execution(
            agent=agent,
            agent_messages=agent_messages,
            tool_calls=tool_calls,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        if not agent_response:
            agent_response = "Sorry, I'm having trouble. Please try again."

        return {
            "agent_response": agent_response,
            "tool_calls": tool_calls,
            "error": None,
        }
    except Exception:
        logger.exception("Orchestrator chat node failed")
        return {
            "agent_response": "Sorry, I'm having trouble. Please try again.",
            "tool_calls": tool_calls,
            "error": "orchestrator_chat_node_failed",
        }


async def _stream_chat_agent_execution(
    agent: Any,
    agent_messages: list[Any],
    tool_calls: list[ToolCallRecord],
    user_id: str,
    conversation_id: str,
) -> str | None:
    """Stream chat agent execution and emit chat/tool events."""
    agent_response = None

    async for event in agent.astream_events({"messages": agent_messages}, version="v2"):
        event_kind = event.get("event", "")

        if event_kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                token = chunk.content
                await gateway.emit_to_user(
                    user_id=user_id,
                    event=ChatEvents.MESSAGE_TOKEN,
                    data={
                        "conversation_id": conversation_id,
                        "token": token,
                    },
                )
        elif event_kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event.get("data", {}).get("input", {})
            run_id = event.get("run_id", "")

            if isinstance(tool_input, dict):
                serializable_input = {
                    k: (
                        str(v)
                        if not isinstance(
                            v, (str, int, float, bool, list, dict, type(None))
                        )
                        else v
                    )
                    for k, v in tool_input.items()
                }
            else:
                serializable_input = {"input": str(tool_input)}

            tool_calls.append(
                {
                    "tool_name": tool_name,
                    "tool_call_id": run_id,
                    "arguments": serializable_input,
                    "result": None,
                    "error": None,
                }
            )

            await gateway.emit_to_user(
                user_id=user_id,
                event=ChatEvents.MESSAGE_TOOL_START,
                data={
                    "conversation_id": conversation_id,
                    "tool_name": tool_name,
                    "tool_call_id": run_id,
                    "arguments": serializable_input,
                },
            )
        elif event_kind == "on_tool_end":
            tool_output = event.get("data", {}).get("output", "")
            run_id = event.get("run_id", "")
            result = str(tool_output) if tool_output else ""

            for tool_call in tool_calls:
                if tool_call["tool_call_id"] == run_id:
                    tool_call["result"] = result
                    break

            await gateway.emit_to_user(
                user_id=user_id,
                event=ChatEvents.MESSAGE_TOOL_END,
                data={
                    "conversation_id": conversation_id,
                    "tool_call_id": run_id,
                    "result": result,
                },
            )
        elif event_kind == "on_chain_end":
            output = event.get("data", {}).get("output", {})
            if isinstance(output, dict) and "messages" in output:
                final_messages = output["messages"]
                for msg in reversed(final_messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        agent_response = msg.content
                        break

    return agent_response
