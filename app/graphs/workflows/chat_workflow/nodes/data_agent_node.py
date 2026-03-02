"""Data agent node for handling data queries.

Emits Socket.IO events directly for real-time streaming to clients.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.implementations.data_agent.agent import create_data_agent
from app.common.event_socket import ChatEvents
from app.graphs.workflows.chat_workflow.state import ChatWorkflowState, ToolCallRecord
from app.socket_gateway import gateway

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


async def data_agent_node(state: ChatWorkflowState) -> dict:
    """Execute Data Agent to handle data queries.

    Creates a ReAct agent with data query tools and invokes it to
    process the user's data-related question. Emits Socket.IO events
    for tool calls and token streaming.

    Args:
        state: Current workflow state containing messages, user_connections, etc.

    Returns:
        dict with:
        - "agent_response": The agent's final response string
        - "tool_calls": List of tool call records
    """
    user_connections = state.get("user_connections", [])
    messages = state.get("messages", [])
    user_id = state.get("user_id", "")
    conversation_id = state.get("conversation_id", "")
    tool_calls: list[ToolCallRecord] = []

    # Check if user has any connections
    if not user_connections:
        logger.warning("User has no connections configured")
        return {
            "agent_response": "You don't have any data synchronized yet. Please establish a Google Sheet connection before querying data.",
            "tool_calls": [],
        }

    # Create agent with user's connections
    agent = create_data_agent(user_connections)

    # Build input messages for agent
    agent_messages = _build_agent_messages(messages)

    # Execute agent with retries
    agent_response = None
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.info("Data agent attempt %d/%d", attempt + 1, MAX_RETRIES)

            # Stream agent execution with Socket.IO emit
            agent_response = await _stream_agent_execution(
                agent=agent,
                agent_messages=agent_messages,
                tool_calls=tool_calls,
                user_id=user_id,
                conversation_id=conversation_id,
            )

            if agent_response:
                logger.info(
                    "Data agent completed successfully: %s...", agent_response[:50]
                )
                break

        except Exception as e:
            last_error = str(e)
            logger.warning("Data agent attempt %d failed: %s", attempt + 1, last_error)

            # Mark last tool call as failed if any
            if tool_calls:
                tool_calls[-1]["error"] = last_error

    # Handle case where all retries failed
    if agent_response is None:
        logger.error("Data agent failed after %d attempts: %s", MAX_RETRIES, last_error)
        agent_response = "Sorry, I'm having trouble querying your data. Please try again or rephrase your question."
    return {
        "agent_response": agent_response,
        "tool_calls": tool_calls,
    }


async def _stream_agent_execution(
    agent: Any,
    agent_messages: list[Any],
    tool_calls: list[ToolCallRecord],
    user_id: str,
    conversation_id: str,
) -> str | None:
    """Stream agent execution, emit Socket.IO events, and capture final response.

    Args:
        agent: The compiled LangGraph agent
        agent_messages: Input messages for the agent
        tool_calls: List to append tool call records to
        user_id: User ID for Socket.IO room targeting
        conversation_id: Conversation ID for event data

    Returns:
        The final agent response string, or None if not found
    """
    agent_response = None
    full_content = ""

    async for event in agent.astream_events(
        {"messages": agent_messages},
        version="v2",
    ):
        event_kind = event.get("event", "")

        # Handle token streaming
        if event_kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
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

        # Handle tool start events
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
            logger.info("Tool started: %s", tool_name)

        # Handle tool end events
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
            logger.info("Tool ended: %s", event.get("name", "unknown"))

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
