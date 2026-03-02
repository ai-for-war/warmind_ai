"""Chat node for handling general conversation with web search capability.

Emits Socket.IO events directly for real-time token streaming and tool events.
Uses chat_agent with MCP tools for web search when needed.

Requirements: 4.1, 4.5, 4.6
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.implementations.chat_agent.agent import create_chat_agent
from app.common.event_socket import ChatEvents
from app.graphs.workflows.chat_workflow.state import ChatWorkflowState, ToolCallRecord
from app.socket_gateway import gateway

logger = logging.getLogger(__name__)


async def chat_node(state: ChatWorkflowState) -> dict:
    """Handle general conversation with the user using chat agent.

    Responds to greetings, questions about capabilities, and general chitchat
    in a friendly manner using Vietnamese language. Can search the web when
    users ask questions requiring current information.

    Streams tokens via Socket.IO and emits tool events for web search operations.

    Args:
        state: Current workflow state containing messages and context

    Returns:
        dict with:
        - "agent_response": The agent's final response string
        - "tool_calls": List of tool call records (for web search operations)

    Requirements:
        - 4.1: Chat_Node upgraded to Chat_Agent with tool calling
        - 4.5: Maintain streaming capability
        - 4.6: Emit tool call events via Socket.IO
    """
    user_id = state.get("user_id", "")
    conversation_id = state.get("conversation_id", "")
    tool_calls: list[ToolCallRecord] = []

    try:
        # Create chat agent with MCP tools (web search capability)
        agent = create_chat_agent()

        # Build input messages for agent
        messages = state.get("messages", [])
        agent_messages = _build_agent_messages(messages)

        # Stream agent execution with Socket.IO emit
        agent_response = await _stream_chat_agent_execution(
            agent=agent,
            agent_messages=agent_messages,
            tool_calls=tool_calls,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        if agent_response:
            logger.info("Chat node generated response: %s...", agent_response[:50])
        else:
            agent_response = "Sorry, I'm having trouble. Please try again."

        return {
            "agent_response": agent_response,
            "tool_calls": tool_calls,
        }

    except Exception:
        logger.exception("Chat node failed")
        return {
            "agent_response": "Sorry, I'm having trouble. Please try again.",
            "tool_calls": tool_calls,
        }


async def _stream_chat_agent_execution(
    agent: Any,
    agent_messages: list[Any],
    tool_calls: list[ToolCallRecord],
    user_id: str,
    conversation_id: str,
) -> str | None:
    """Stream chat agent execution, emit Socket.IO events, and capture response.

    Handles token streaming for real-time response display and emits tool events
    when the agent uses web search or fetch content tools.

    Args:
        agent: The compiled LangGraph chat agent
        agent_messages: Input messages for the agent
        tool_calls: List to append tool call records to
        user_id: User ID for Socket.IO room targeting
        conversation_id: Conversation ID for event data

    Returns:
        The final agent response string, or None if not found

    Requirements:
        - 4.5: Maintain streaming capability
        - 4.6: Emit tool_start and tool_end events via Socket.IO
    """
    agent_response = None

    async for event in agent.astream_events(
        {"messages": agent_messages},
        version="v2",
    ):
        event_kind = event.get("event", "")

        # Handle token streaming (Requirement 4.5)
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

        # Handle tool start events (Requirement 4.6)
        elif event_kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event.get("data", {}).get("input", {})
            run_id = event.get("run_id", "")

            # Ensure tool_input is JSON serializable
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

            tool_call_record: ToolCallRecord = {
                "tool_name": tool_name,
                "tool_call_id": run_id,
                "arguments": serializable_input,
                "result": None,
                "error": None,
            }
            tool_calls.append(tool_call_record)

            # Emit tool start event
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
            logger.info("Chat agent tool started: %s", tool_name)

        # Handle tool end events (Requirement 4.6)
        elif event_kind == "on_tool_end":
            tool_output = event.get("data", {}).get("output", "")
            run_id = event.get("run_id", "")
            result = str(tool_output) if tool_output else ""

            # Update the matching tool call record
            for tc in tool_calls:
                if tc["tool_call_id"] == run_id:
                    tc["result"] = result
                    break

            # Emit tool end event
            await gateway.emit_to_user(
                user_id=user_id,
                event=ChatEvents.MESSAGE_TOOL_END,
                data={
                    "conversation_id": conversation_id,
                    "tool_call_id": run_id,
                    "result": result,
                },
            )
            logger.info("Chat agent tool ended: %s", event.get("name", "unknown"))

        # Capture final response from chain end
        elif event_kind == "on_chain_end":
            output = event.get("data", {}).get("output", {})

            # Extract messages from output
            if isinstance(output, dict) and "messages" in output:
                final_messages = output["messages"]
                # Get the last AI message
                for msg in reversed(final_messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        agent_response = msg.content
                        break

    return agent_response


def _build_agent_messages(messages: list[Any]) -> list[Any]:
    """Build message list for agent from workflow state messages.

    Args:
        messages: List of messages from workflow state

    Returns:
        List of messages suitable for agent input
    """
    agent_messages = []

    for msg in messages[-10:]:  # Last 10 messages for context
        if hasattr(msg, "content"):
            if isinstance(msg, HumanMessage) or (
                hasattr(msg, "type") and msg.type == "human"
            ):
                agent_messages.append(HumanMessage(content=msg.content))
            elif isinstance(msg, AIMessage) or (
                hasattr(msg, "type") and msg.type == "ai"
            ):
                agent_messages.append(AIMessage(content=msg.content))

    return agent_messages
