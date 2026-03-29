"""Lead-agent service for checkpoint-backed conversation projections."""

import logging
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.lead_agent.agent import create_lead_agent
from app.common.event_socket import ChatEvents
from app.common.exceptions import AppException
from app.common.exceptions.ai_exceptions import (
    InvalidLeadAgentThreadError,
    LeadAgentConversationNotFoundError,
    LeadAgentRunError,
    LeadAgentThreadNotFoundError,
)
from app.domain.models.conversation import Conversation, ConversationStatus
from app.domain.models.message import Message, MessageMetadata, MessageRole, ToolCall
from app.repo.conversation_repo import SearchResult
from app.services.ai.conversation_service import ConversationService
from app.services.ai.lead_agent_skill_access_resolver import (
    LeadAgentSkillAccessResolver,
)
from app.socket_gateway import gateway

logger = logging.getLogger(__name__)


class LeadAgentService:
    """Manage lead-agent conversations backed by LangGraph checkpoints."""

    def __init__(
        self,
        conversation_service: ConversationService,
        skill_access_resolver: LeadAgentSkillAccessResolver | None = None,
    ) -> None:
        """Initialize the service with shared persistence helpers."""
        self.conversation_service = conversation_service
        self.skill_access_resolver = skill_access_resolver
        self._agent: CompiledStateGraph | None = None

    @property
    def agent(self) -> CompiledStateGraph:
        """Return the cached lead-agent runtime."""
        if self._agent is None:
            self._agent = create_lead_agent()
        return self._agent

    async def create_thread(
        self,
        user_id: str,
        organization_id: str | None = None,
    ) -> str:
        """Compatibility wrapper for the legacy thread-creation route."""
        return await self._create_thread(
            user_id=user_id,
            organization_id=organization_id,
        )

    async def run_thread(
        self,
        thread_id: str,
        user_id: str,
        content: str,
        organization_id: str | None = None,
    ) -> str:
        """Compatibility wrapper for the legacy thread-run route."""
        normalized_content = self._normalize_content(content)
        normalized_thread_id = await self._validate_thread_for_caller(
            thread_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        result = await self._invoke_thread(
            thread_id=normalized_thread_id,
            user_id=user_id,
            content=normalized_content,
            organization_id=organization_id,
        )
        return self._extract_final_response(result)

    async def send_message(
        self,
        user_id: str,
        content: str,
        conversation_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """Persist a lead-agent user turn and return message/conversation IDs."""
        normalized_content = self._normalize_content(content)
        conversation, thread_id = await self._get_or_create_conversation_projection(
            user_id=user_id,
            initial_message_content=normalized_content,
            conversation_id=conversation_id,
            organization_id=organization_id,
        )
        user_message = await self.conversation_service.add_message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=normalized_content,
            organization_id=organization_id,
            thread_id=thread_id,
        )
        return user_message.id, conversation.id

    async def process_agent_response(
        self,
        user_id: str,
        conversation_id: str,
        user_message_id: str,
        organization_id: Optional[str] = None,
    ) -> None:
        """Run the lead-agent runtime in the background and stream socket events."""
        try:
            await gateway.emit_to_user(
                user_id=user_id,
                event=ChatEvents.MESSAGE_STARTED,
                data={"conversation_id": conversation_id},
                organization_id=organization_id,
            )

            _, thread_id = await self._require_lead_agent_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                organization_id=organization_id,
                validate_thread_state=True,
            )
            user_message = await self._require_user_message(
                user_message_id=user_message_id,
                conversation_id=conversation_id,
                thread_id=thread_id,
            )

            tool_calls = await self._stream_thread_execution(
                thread_id=thread_id,
                user_id=user_id,
                conversation_id=conversation_id,
                content=user_message.content,
                organization_id=organization_id,
            )
            response_content = await self._get_thread_response_for_caller(
                thread_id=thread_id,
                user_id=user_id,
                organization_id=organization_id,
            )
            assistant_metadata = self._build_assistant_metadata(tool_calls)
            assistant_message = await self.conversation_service.add_message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=response_content,
                organization_id=organization_id,
                metadata=assistant_metadata,
                thread_id=thread_id,
            )
            metadata_payload = (
                assistant_message.metadata.model_dump(exclude_none=True)
                if assistant_message.metadata is not None
                else None
            )
            if not metadata_payload:
                metadata_payload = None

            await gateway.emit_to_user(
                user_id=user_id,
                event=ChatEvents.MESSAGE_COMPLETED,
                data={
                    "conversation_id": conversation_id,
                    "message_id": assistant_message.id,
                    "content": response_content,
                    "metadata": metadata_payload,
                },
                organization_id=organization_id,
            )
        except Exception as exc:
            logger.exception(
                "Error processing lead-agent response for conversation %s",
                conversation_id,
            )
            await gateway.emit_to_user(
                user_id=user_id,
                event=ChatEvents.MESSAGE_FAILED,
                data={
                    "conversation_id": conversation_id,
                    "error": str(exc),
                },
                organization_id=organization_id,
            )

    async def search_conversations(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> SearchResult:
        """Return only lead-agent conversations for the authenticated caller."""
        return await self.conversation_service.search_user_conversations(
            user_id=user_id,
            organization_id=organization_id,
            has_thread_id=True,
            status=status,
            search=search,
            skip=skip,
            limit=limit,
        )

    async def get_conversation_messages(
        self,
        conversation_id: str,
        user_id: str,
        organization_id: Optional[str] = None,
    ) -> list[Message]:
        """Return persisted messages for a lead-agent conversation."""
        conversation, _ = await self._require_lead_agent_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
            validate_thread_state=False,
        )
        return await self.conversation_service.get_messages(
            conversation_id=conversation.id,
        )

    async def _get_or_create_conversation_projection(
        self,
        user_id: str,
        initial_message_content: str,
        conversation_id: Optional[str],
        organization_id: Optional[str],
    ) -> tuple[Conversation, str]:
        """Create or load the lead-agent conversation projection for a send."""
        if conversation_id is None:
            thread_id = await self._create_thread(
                user_id=user_id,
                organization_id=organization_id,
            )
            conversation = (
                await self.conversation_service.create_conversation_from_initial_message(
                    user_id=user_id,
                    content=initial_message_content,
                    organization_id=organization_id,
                    thread_id=thread_id,
                )
            )
            return conversation, thread_id

        return await self._require_lead_agent_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
            validate_thread_state=True,
        )

    async def _require_lead_agent_conversation(
        self,
        conversation_id: str,
        user_id: str,
        organization_id: Optional[str],
        validate_thread_state: bool,
    ) -> tuple[Conversation, str]:
        """Load a caller-scoped conversation and return its validated thread ID."""
        conversation = await self.conversation_service.get_user_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
            has_thread_id=True,
        )
        if conversation is None or not conversation.thread_id:
            raise LeadAgentConversationNotFoundError()

        try:
            thread_id = self._normalize_thread_id(conversation.thread_id)
            if validate_thread_state:
                state = await self._get_thread_state(thread_id)
                self._validate_thread_scope(
                    state,
                    user_id=user_id,
                    organization_id=organization_id,
                )
        except (InvalidLeadAgentThreadError, LeadAgentThreadNotFoundError) as exc:
            raise LeadAgentConversationNotFoundError() from exc

        return conversation, thread_id

    async def _create_thread(
        self,
        user_id: str,
        organization_id: Optional[str],
    ) -> str:
        """Create a new checkpoint-backed thread and seed caller scope."""
        thread_id = str(uuid4())
        config = self._thread_config(thread_id)
        initial_state = {
            "messages": [],
            "user_id": user_id,
            "organization_id": organization_id,
        }

        await self.agent.aupdate_state(
            config,
            values=initial_state,
            as_node="__start__",
        )
        return thread_id

    async def _validate_thread_for_caller(
        self,
        thread_id: str,
        user_id: str,
        organization_id: Optional[str],
    ) -> str:
        """Validate that a thread exists and belongs to the authenticated caller."""
        normalized_thread_id = self._normalize_thread_id(thread_id)
        state = await self._get_thread_state(normalized_thread_id)
        self._validate_thread_scope(
            state,
            user_id=user_id,
            organization_id=organization_id,
        )
        return normalized_thread_id

    async def _invoke_thread(
        self,
        thread_id: str,
        user_id: str,
        content: str,
        organization_id: Optional[str],
    ) -> dict[str, Any]:
        """Invoke a checkpoint-backed thread with a new user message."""
        return await self.agent.ainvoke(
            {
                "messages": [{"role": "user", "content": content}],
                "user_id": user_id,
                "organization_id": organization_id,
            },
            config=self._thread_config(thread_id),
        )

    async def _stream_thread_execution(
        self,
        thread_id: str,
        user_id: str,
        conversation_id: str,
        content: str,
        organization_id: Optional[str],
    ) -> list[dict[str, Any]]:
        """Stream the lead-agent runtime and emit chat-compatible socket events."""
        tool_calls: list[dict[str, Any]] = []

        async for event in self.agent.astream_events(
            {
                "messages": [{"role": "user", "content": content}],
                "user_id": user_id,
                "organization_id": organization_id,
            },
            config=self._thread_config(thread_id),
            version="v2",
        ):
            event_kind = event.get("event", "")

            if event_kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                token = self._message_content_to_text(chunk)
                if token:
                    await gateway.emit_to_user(
                        user_id=user_id,
                        event=ChatEvents.MESSAGE_TOKEN,
                        data={
                            "conversation_id": conversation_id,
                            "token": token,
                        },
                        organization_id=organization_id,
                    )
            elif event_kind == "on_tool_start":
                run_id = str(event.get("run_id", ""))
                serializable_input = self._serialize_tool_arguments(
                    event.get("data", {}).get("input", {})
                )
                tool_call = {
                    "tool_name": event.get("name", "unknown"),
                    "tool_call_id": run_id,
                    "arguments": serializable_input,
                    "result": None,
                    "error": None,
                }
                tool_calls.append(tool_call)
                await gateway.emit_to_user(
                    user_id=user_id,
                    event=ChatEvents.MESSAGE_TOOL_START,
                    data={
                        "conversation_id": conversation_id,
                        "tool_name": tool_call["tool_name"],
                        "tool_call_id": run_id,
                        "arguments": serializable_input,
                    },
                    organization_id=organization_id,
                )
            elif event_kind == "on_tool_end":
                run_id = str(event.get("run_id", ""))
                result = self._tool_output_to_text(
                    event.get("data", {}).get("output", "")
                )
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
                    organization_id=organization_id,
                )

        return tool_calls

    async def _require_user_message(
        self,
        user_message_id: str,
        conversation_id: str,
        thread_id: str,
    ) -> Message:
        """Load the accepted user message that should be replayed into runtime state."""
        message = await self.conversation_service.get_message(user_message_id)
        if message is None:
            raise LeadAgentRunError("Lead-agent user message not found")
        if message.conversation_id != conversation_id:
            raise LeadAgentRunError("Lead-agent user message does not match conversation")
        if message.role != MessageRole.USER:
            raise LeadAgentRunError("Lead-agent user message is not a user turn")
        if message.thread_id != thread_id:
            raise LeadAgentRunError("Lead-agent user message does not match thread")
        return message

    async def _get_thread_response_for_caller(
        self,
        thread_id: str,
        user_id: str,
        organization_id: Optional[str],
    ) -> str:
        """Load the checkpoint state after execution and extract the final reply."""
        state = await self._get_thread_state(thread_id)
        self._validate_thread_scope(
            state,
            user_id=user_id,
            organization_id=organization_id,
        )
        return self._extract_final_response(state)

    async def _get_thread_state(self, thread_id: str) -> dict[str, Any]:
        """Load the latest checkpointed state for a thread."""
        snapshot = await self.agent.aget_state(self._thread_config(thread_id))
        values = getattr(snapshot, "values", None)
        if not values:
            raise LeadAgentThreadNotFoundError()

        state = dict(values)
        if not state.get("user_id"):
            raise LeadAgentThreadNotFoundError()

        return state

    def _validate_thread_scope(
        self,
        state: dict[str, Any],
        user_id: str,
        organization_id: Optional[str],
    ) -> None:
        """Ensure the checkpointed thread belongs to the authenticated caller."""
        if state.get("user_id") != user_id:
            raise LeadAgentThreadNotFoundError()

        if state.get("organization_id") != organization_id:
            raise LeadAgentThreadNotFoundError()

    @staticmethod
    def _thread_config(thread_id: str) -> dict[str, dict[str, str]]:
        """Build LangGraph config for a thread."""
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _normalize_thread_id(thread_id: str) -> str:
        """Validate and normalize a thread identifier."""
        try:
            return str(UUID(thread_id))
        except ValueError as exc:
            raise InvalidLeadAgentThreadError() from exc

    @staticmethod
    def _normalize_content(content: str) -> str:
        """Validate and normalize incoming message content."""
        normalized_content = content.strip()
        if not normalized_content:
            raise AppException("Content is required")
        return normalized_content

    @staticmethod
    def _serialize_tool_arguments(tool_input: Any) -> dict[str, Any]:
        """Convert tool input into a JSON-safe dict payload."""
        encoded_input = jsonable_encoder(tool_input)
        if isinstance(encoded_input, dict):
            return encoded_input
        return {"input": encoded_input}

    @classmethod
    def _tool_output_to_text(cls, output: Any) -> str:
        """Convert streamed tool output into a user-facing string."""
        encoded_output = jsonable_encoder(output)
        text = cls._content_to_text(encoded_output).strip()
        if text:
            return text
        if encoded_output is None:
            return ""
        return str(encoded_output)

    @staticmethod
    def _build_assistant_metadata(
        tool_calls: list[dict[str, Any]],
    ) -> Optional[MessageMetadata]:
        """Build persisted assistant metadata from streamed tool activity."""
        if not tool_calls:
            return None

        return MessageMetadata(
            tool_calls=[
                ToolCall(
                    id=tool_call["tool_call_id"],
                    name=tool_call["tool_name"],
                    arguments=tool_call["arguments"],
                )
                for tool_call in tool_calls
            ]
        )

    def _extract_final_response(self, result: dict[str, Any]) -> str:
        """Extract the final assistant response from an agent run result."""
        messages = result.get("messages") if isinstance(result, dict) else None
        if not messages:
            raise LeadAgentRunError()

        for message in reversed(messages):
            if self._is_assistant_message(message):
                response = self._message_content_to_text(message)
                if response:
                    return response

        fallback_response = self._message_content_to_text(messages[-1])
        if fallback_response:
            return fallback_response

        raise LeadAgentRunError()

    @staticmethod
    def _is_assistant_message(message: Any) -> bool:
        """Return True when a message is an assistant/AI message."""
        if isinstance(message, dict):
            return message.get("role") == "assistant"

        if getattr(message, "type", None) == "ai":
            return True

        if getattr(message, "role", None) == "assistant":
            return True

        return message.__class__.__name__ == "AIMessage"

    @classmethod
    def _message_content_to_text(cls, message: Any) -> str:
        """Normalize message content into a plain-text response."""
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)

        return cls._content_to_text(content).strip()

    @classmethod
    def _content_to_text(cls, content: Any) -> str:
        """Convert structured message content into text."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = [cls._content_to_text(item).strip() for item in content]
            return "\n".join(part for part in parts if part)

        if isinstance(content, dict):
            if "text" in content and content["text"] is not None:
                return str(content["text"])
            if "content" in content:
                return cls._content_to_text(content["content"])
            return ""

        if content is None:
            return ""

        return str(content)
