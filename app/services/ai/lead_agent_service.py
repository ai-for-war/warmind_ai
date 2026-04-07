"""Lead-agent service for checkpoint-backed conversation projections."""

import logging
from dataclasses import is_dataclass
from collections.abc import Mapping, Sequence
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.lead_agent.agent import create_lead_agent
from app.agents.implementations.lead_agent.runtime import (
    LeadAgentRuntimeConfig,
    resolve_lead_agent_runtime_config,
)
from app.common.event_socket import ChatEvents
from app.common.exceptions import AppException
from app.common.exceptions.ai_exceptions import (
    InvalidLeadAgentThreadError,
    LeadAgentConversationNotFoundError,
    LeadAgentRunError,
    LeadAgentThreadNotFoundError,
)
from app.domain.models.conversation import Conversation, ConversationStatus
from app.domain.models.message import (
    Message,
    MessageMetadata,
    MessageRole,
    TokenUsage,
    ToolCall,
)
from app.repo.conversation_repo import SearchResult
from app.services.ai.conversation_service import ConversationService
from app.services.ai.lead_agent_skill_access_resolver import (
    LeadAgentSkillAccessResolver,
    ResolvedLeadAgentSkillAccess,
)
from app.socket_gateway import gateway

logger = logging.getLogger(__name__)

LEAD_AGENT_RECURSION_LIMIT = 200
FILTERED_TOOL_ARGUMENT_KEYS = frozenset({"runtime"})
ORCHESTRATION_MODE_DIRECT = "direct"
ORCHESTRATION_MODE_SUBAGENT = "subagent"


class LeadAgentService:
    """Manage lead-agent conversations backed by LangGraph checkpoints."""

    def __init__(
        self,
        conversation_service: ConversationService,
        skill_access_resolver: LeadAgentSkillAccessResolver | None = None,
        runtime_config: LeadAgentRuntimeConfig | None = None,
    ) -> None:
        """Initialize the service with shared persistence helpers."""
        self.conversation_service = conversation_service
        self.skill_access_resolver = skill_access_resolver
        self.runtime_config = runtime_config
        self._agent: CompiledStateGraph | None = None

    @property
    def agent(self) -> CompiledStateGraph:
        """Return the lazily built lead-agent runtime for this service instance."""
        if self._agent is None:
            self._agent = create_lead_agent(self.runtime_config)
        return self._agent

    def configure_runtime(
        self,
        *,
        provider: str,
        model: str,
        reasoning: str | None = None,
    ) -> LeadAgentRuntimeConfig:
        """Resolve and pin the runtime config for this service instance."""
        self.runtime_config = resolve_lead_agent_runtime_config(
            provider=provider,
            model=model,
            reasoning=reasoning,
        )
        self._agent = None
        return self.runtime_config

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
        subagent_enabled: bool = False,
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
            metadata=self._build_user_message_metadata(
                subagent_enabled=subagent_enabled
            ),
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

            tool_calls, model_response_metadata = await self._stream_thread_execution(
                thread_id=thread_id,
                user_id=user_id,
                conversation_id=conversation_id,
                content=user_message.content,
                organization_id=organization_id,
                subagent_enabled=self._extract_subagent_enabled_from_message(
                    user_message
                ),
            )
            final_state = await self._get_thread_state_for_caller(
                thread_id=thread_id,
                user_id=user_id,
                organization_id=organization_id,
            )
            response_content = self._extract_final_response(final_state)
            assistant_metadata = self._build_assistant_metadata(
                tool_calls=tool_calls,
                final_state=final_state,
                runtime_config=self.runtime_config,
                tokens=model_response_metadata.get("tokens"),
                finish_reason=model_response_metadata.get("finish_reason"),
            )
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

            logger.info(
                "Completed lead-agent turn for conversation %s (thread_id=%s, skill_id=%s, skill_version=%s, loaded_skills=%s, tool_calls=%d)",
                conversation_id,
                thread_id,
                final_state.get("active_skill_id"),
                final_state.get("active_skill_version"),
                final_state.get("loaded_skills", []),
                len(tool_calls),
            )

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

    async def get_conversation_plan(
        self,
        conversation_id: str,
        user_id: str,
        organization_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return the latest persisted todo snapshot for a lead-agent conversation."""
        _, thread_id = await self._require_lead_agent_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
            validate_thread_state=True,
        )
        todos = await self._get_persisted_todo_snapshot_for_caller(
            thread_id=thread_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        return self._build_plan_update_payload(
            conversation_id=conversation_id,
            todos=todos,
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
            conversation = await self.conversation_service.create_conversation_from_initial_message(
                user_id=user_id,
                content=initial_message_content,
                organization_id=organization_id,
                thread_id=thread_id,
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
            "subagent_enabled": False,
            "orchestration_mode": ORCHESTRATION_MODE_DIRECT,
            "delegation_depth": 0,
            "delegation_parent_run_id": None,
            "delegated_execution_metadata": None,
            "enabled_skill_ids": [],
            "loaded_skills": [],
            "allowed_tool_names": [],
            "active_skill_id": None,
            "active_skill_version": None,
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
        subagent_enabled: bool = False,
    ) -> dict[str, Any]:
        """Invoke a checkpoint-backed thread with a new user message."""
        runtime_payload = await self._build_runtime_payload(
            thread_id=thread_id,
            user_id=user_id,
            content=content,
            organization_id=organization_id,
            subagent_enabled=subagent_enabled,
        )
        return await self.agent.ainvoke(
            runtime_payload,
            config=self._thread_config(thread_id),
        )

    async def _stream_thread_execution(
        self,
        thread_id: str,
        user_id: str,
        conversation_id: str,
        content: str,
        organization_id: Optional[str],
        subagent_enabled: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Stream the lead-agent runtime and emit chat-compatible socket events."""
        tool_calls: list[dict[str, Any]] = []
        aggregated_tokens = TokenUsage()
        has_token_usage = False
        finish_reason: str | None = None
        runtime_payload = await self._build_runtime_payload(
            thread_id=thread_id,
            user_id=user_id,
            content=content,
            organization_id=organization_id,
            subagent_enabled=subagent_enabled,
        )
        async for event in self.agent.astream_events(
            runtime_payload,
            config=self._thread_config(thread_id),
            version="v2",
        ):
            event_kind = event.get("event", "")

            if event_kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                token = self._message_content_to_stream_token(chunk)
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
            elif event_kind == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                token_usage = self._extract_token_usage(output)
                if token_usage is not None:
                    aggregated_tokens.prompt += token_usage.prompt
                    aggregated_tokens.completion += token_usage.completion
                    aggregated_tokens.total += token_usage.total
                    has_token_usage = True
                finish_reason = self._extract_finish_reason(output) or finish_reason
            elif event_kind == "on_tool_start":
                run_id = str(event.get("run_id", ""))
                tool_name = str(event.get("name", "unknown"))
                serializable_input = self._serialize_tool_arguments(
                    event.get("data", {}).get("input", {})
                )
                tool_call = {
                    "tool_name": tool_name,
                    "tool_call_id": run_id,
                    "arguments": serializable_input,
                    "result": None,
                    "error": None,
                }
                tool_calls.append(tool_call)
                if tool_name != "write_todos":
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
                completed_tool_name, completed_tool_call = self._finalize_tool_call(
                    tool_calls,
                    tool_call_id=run_id,
                    result=result,
                    error=None,
                )

                if completed_tool_name != "write_todos":
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
                if (
                    completed_tool_name == "write_todos"
                    and completed_tool_call is not None
                ):
                    current_todos = self._extract_todo_snapshot(
                        {"todos": completed_tool_call["arguments"].get("todos", [])}
                    )
                    await gateway.emit_to_user(
                        user_id=user_id,
                        event=ChatEvents.MESSAGE_PLAN_UPDATED,
                        data=self._build_plan_update_payload(
                            conversation_id=conversation_id,
                            todos=current_todos,
                        ),
                        organization_id=organization_id,
                    )
            elif event_kind == "on_tool_error":
                run_id = str(event.get("run_id", ""))
                error_text = self._tool_error_to_text(
                    event.get("data", {}).get("error", "")
                )
                completed_tool_name, _ = self._finalize_tool_call(
                    tool_calls,
                    tool_call_id=run_id,
                    result=error_text,
                    error=error_text,
                )

                if completed_tool_name != "write_todos":
                    await gateway.emit_to_user(
                        user_id=user_id,
                        event=ChatEvents.MESSAGE_TOOL_END,
                        data={
                            "conversation_id": conversation_id,
                            "tool_call_id": run_id,
                            "result": error_text,
                            "error": error_text,
                        },
                        organization_id=organization_id,
                    )

        return tool_calls, {
            "tokens": aggregated_tokens if has_token_usage else None,
            "finish_reason": finish_reason,
        }

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
            raise LeadAgentRunError(
                "Lead-agent user message does not match conversation"
            )
        if message.role != MessageRole.USER:
            raise LeadAgentRunError("Lead-agent user message is not a user turn")
        if message.thread_id != thread_id:
            raise LeadAgentRunError("Lead-agent user message does not match thread")
        return message

    async def _get_thread_state_for_caller(
        self,
        thread_id: str,
        user_id: str,
        organization_id: Optional[str],
    ) -> dict[str, Any]:
        """Load the checkpoint state after execution for the authenticated caller."""
        state = await self._get_thread_state(thread_id)
        self._validate_thread_scope(
            state,
            user_id=user_id,
            organization_id=organization_id,
        )
        return state

    async def _get_persisted_todo_snapshot_for_caller(
        self,
        *,
        thread_id: str,
        user_id: str,
        organization_id: Optional[str],
    ) -> list[dict[str, Any]]:
        """Load the latest persisted todo snapshot for one caller-scoped thread."""
        state = await self._get_thread_state_for_caller(
            thread_id=thread_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        return self._extract_todo_snapshot(state)

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
    def _thread_config(thread_id: str) -> dict[str, Any]:
        """Build LangGraph config for a thread."""
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": LEAD_AGENT_RECURSION_LIMIT,
        }

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
        encoded_input = LeadAgentService._make_json_safe(tool_input)
        if isinstance(encoded_input, dict):
            return encoded_input
        return {"input": encoded_input}

    @classmethod
    def _tool_output_to_text(cls, output: Any) -> str:
        """Convert streamed tool output into a user-facing string."""
        encoded_output = cls._make_json_safe(output)
        text = cls._content_to_text(encoded_output).strip()
        if text:
            return text
        if encoded_output is None:
            return ""
        return str(encoded_output)

    @staticmethod
    def _tool_error_to_text(error: Any) -> str:
        """Convert one streamed tool error into readable text."""
        if error is None:
            return ""
        if isinstance(error, BaseException):
            return str(error).strip()
        return str(error).strip()

    @classmethod
    def _make_json_safe(cls, value: Any) -> Any:
        """Best-effort conversion of tool payloads into JSON-safe values."""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, Mapping):
            normalized_mapping: dict[str, Any] = {}
            for key, item in value.items():
                normalized_key = str(key)
                if normalized_key in FILTERED_TOOL_ARGUMENT_KEYS:
                    continue
                normalized_mapping[normalized_key] = cls._make_json_safe(item)
            return normalized_mapping
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            return [cls._make_json_safe(item) for item in value]
        if is_dataclass(value):
            return cls._make_json_safe(vars(value))
        if hasattr(value, "__dict__"):
            object_vars = vars(value)
            if object_vars:
                return cls._make_json_safe(object_vars)

        try:
            encoded_value = jsonable_encoder(value)
        except (TypeError, ValueError):
            return str(value)

        if encoded_value is value:
            return str(value)
        if encoded_value in ({}, []) and not isinstance(value, (Mapping, Sequence)):
            return str(value)

        return cls._make_json_safe(encoded_value)

    @staticmethod
    def _build_assistant_metadata(
        *,
        tool_calls: list[dict[str, Any]],
        final_state: dict[str, Any],
        runtime_config: LeadAgentRuntimeConfig | None,
        tokens: TokenUsage | None = None,
        finish_reason: str | None = None,
    ) -> Optional[MessageMetadata]:
        """Build persisted assistant metadata from streamed tool activity."""
        metadata = MessageMetadata(
            model=runtime_config.model if runtime_config is not None else None,
            tokens=tokens,
            finish_reason=finish_reason,
            tool_calls=[
                ToolCall(
                    id=tool_call["tool_call_id"],
                    name=tool_call["tool_name"],
                    arguments=tool_call["arguments"],
                )
                for tool_call in tool_calls
            ]
            or None,
            skill_id=LeadAgentService._normalize_optional_string(
                final_state.get("active_skill_id")
            ),
            skill_version=LeadAgentService._normalize_optional_string(
                final_state.get("active_skill_version")
            ),
            loaded_skills=LeadAgentService._normalize_string_list(
                final_state.get("loaded_skills", [])
            )
            or None,
            subagent_enabled=LeadAgentService._normalize_optional_bool(
                final_state.get("subagent_enabled")
            ),
            orchestration_mode=LeadAgentService._normalize_optional_string(
                final_state.get("orchestration_mode")
            ),
            delegation_depth=LeadAgentService._normalize_optional_int(
                final_state.get("delegation_depth")
            ),
            delegation_parent_run_id=LeadAgentService._normalize_optional_string(
                final_state.get("delegation_parent_run_id")
            ),
            delegated_execution_metadata=LeadAgentService._normalize_optional_mapping(
                final_state.get("delegated_execution_metadata")
            ),
        )
        if not any(
            [
                metadata.model is not None,
                metadata.tokens is not None,
                metadata.finish_reason is not None,
                metadata.tool_calls is not None,
                metadata.skill_id is not None,
                metadata.skill_version is not None,
                metadata.loaded_skills is not None,
                metadata.subagent_enabled is not None,
                metadata.orchestration_mode is not None,
                metadata.delegation_depth is not None,
                metadata.delegation_parent_run_id is not None,
                metadata.delegated_execution_metadata is not None,
            ]
        ):
            return None

        return metadata

    @staticmethod
    def _finalize_tool_call(
        tool_calls: list[dict[str, Any]],
        *,
        tool_call_id: str,
        result: str | None,
        error: str | None,
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Update one tracked tool call from a streamed completion event."""
        for tool_call in tool_calls:
            if tool_call["tool_call_id"] != tool_call_id:
                continue
            tool_call["result"] = result
            tool_call["error"] = error
            return str(tool_call["tool_name"]), tool_call
        return None, None

    async def _build_runtime_payload(
        self,
        *,
        thread_id: str,
        user_id: str,
        content: str,
        organization_id: Optional[str],
        subagent_enabled: bool = False,
        delegation_depth: int = 0,
        delegation_parent_run_id: str | None = None,
        delegated_execution_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build one turn payload with refreshed skill-access state."""
        current_state = await self._get_thread_state(thread_id)
        resolved_access = await self._resolve_skill_access_for_turn(
            user_id=user_id,
            organization_id=organization_id,
        )
        enabled_skill_ids = self._normalize_string_list(
            resolved_access.enabled_skill_ids
        )
        active_skill_id = self._normalize_optional_string(
            current_state.get("active_skill_id")
        )
        if active_skill_id not in enabled_skill_ids:
            active_skill_id = None

        normalized_subagent_enabled = bool(subagent_enabled)
        return {
            "messages": [{"role": "user", "content": content}],
            "user_id": user_id,
            "organization_id": organization_id,
            "subagent_enabled": normalized_subagent_enabled,
            "orchestration_mode": self._resolve_orchestration_mode(
                normalized_subagent_enabled
            ),
            "delegation_depth": max(0, int(delegation_depth)),
            "delegation_parent_run_id": self._normalize_optional_string(
                delegation_parent_run_id
            ),
            "delegated_execution_metadata": self._normalize_optional_mapping(
                delegated_execution_metadata
            ),
            "enabled_skill_ids": enabled_skill_ids,
            "active_skill_id": active_skill_id,
            "loaded_skills": self._normalize_string_list(
                current_state.get("loaded_skills", [])
            ),
            "allowed_tool_names": (
                self._normalize_string_list(current_state.get("allowed_tool_names", []))
                if active_skill_id
                else []
            ),
            "active_skill_version": (
                self._normalize_optional_string(
                    current_state.get("active_skill_version")
                )
                if active_skill_id
                else None
            ),
        }

    async def _resolve_skill_access_for_turn(
        self,
        *,
        user_id: str,
        organization_id: Optional[str],
    ) -> ResolvedLeadAgentSkillAccess:
        """Resolve enabled skills for one runtime turn."""
        if self.skill_access_resolver is None or organization_id is None:
            return ResolvedLeadAgentSkillAccess(enabled_skill_ids=[])

        return await self.skill_access_resolver.resolve_for_caller(
            user_id=user_id,
            organization_id=organization_id,
        )

    @staticmethod
    def _normalize_string_list(values: Any) -> list[str]:
        """Normalize one ordered list of strings while dropping blanks."""
        if not isinstance(values, list):
            return []

        normalized_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized_value = str(value).strip()
            if not normalized_value or normalized_value in seen:
                continue
            seen.add(normalized_value)
            normalized_values.append(normalized_value)
        return normalized_values

    @staticmethod
    def _normalize_optional_string(value: Any) -> str | None:
        """Normalize one optional string value."""
        if value is None:
            return None
        normalized_value = str(value).strip()
        return normalized_value or None

    @staticmethod
    def _normalize_optional_bool(value: Any) -> bool | None:
        """Normalize one optional boolean value."""
        if isinstance(value, bool):
            return value
        return None

    @staticmethod
    def _normalize_optional_int(value: Any) -> int | None:
        """Normalize one optional non-negative integer value."""
        if value is None:
            return None
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            return None
        return normalized_value if normalized_value >= 0 else None

    @classmethod
    def _normalize_optional_mapping(cls, value: Any) -> dict[str, Any] | None:
        """Normalize one optional mapping into a JSON-safe dictionary."""
        if not isinstance(value, Mapping):
            return None
        normalized_value = cls._make_json_safe(value)
        if isinstance(normalized_value, dict):
            return normalized_value
        return None

    @classmethod
    def _build_user_message_metadata(
        cls,
        *,
        subagent_enabled: bool = False,
    ) -> MessageMetadata:
        """Persist the turn-scoped orchestration request on the user message."""
        normalized_subagent_enabled = bool(subagent_enabled)
        return MessageMetadata(
            subagent_enabled=normalized_subagent_enabled,
            orchestration_mode=cls._resolve_orchestration_mode(
                normalized_subagent_enabled
            ),
        )

    @staticmethod
    def _extract_subagent_enabled_from_message(message: Message) -> bool:
        """Resolve the turn-scoped orchestration flag from persisted user metadata."""
        metadata = message.metadata
        if metadata is None:
            return False
        if metadata.subagent_enabled is not None:
            return metadata.subagent_enabled
        return metadata.orchestration_mode == ORCHESTRATION_MODE_SUBAGENT

    @staticmethod
    def _resolve_orchestration_mode(subagent_enabled: bool) -> str:
        """Map the turn-scoped orchestration flag to a runtime mode string."""
        return (
            ORCHESTRATION_MODE_SUBAGENT
            if subagent_enabled
            else ORCHESTRATION_MODE_DIRECT
        )

    @classmethod
    def _extract_token_usage(cls, model_output: Any) -> TokenUsage | None:
        """Extract normalized token usage from one model end payload."""
        usage_metadata = cls._extract_output_field(model_output, "usage_metadata")
        prompt_tokens = cls._extract_int_value(
            usage_metadata,
            primary_key="input_tokens",
            fallback_key="prompt_tokens",
        )
        completion_tokens = cls._extract_int_value(
            usage_metadata,
            primary_key="output_tokens",
            fallback_key="completion_tokens",
        )
        total_tokens = cls._extract_int_value(
            usage_metadata,
            primary_key="total_tokens",
            fallback_key="total_tokens",
        )

        response_metadata = cls._extract_output_field(model_output, "response_metadata")
        token_usage = cls._extract_output_field(response_metadata, "token_usage")
        if prompt_tokens == 0:
            prompt_tokens = cls._extract_int_value(
                token_usage,
                primary_key="prompt_tokens",
                fallback_key="input_tokens",
            )
        if completion_tokens == 0:
            completion_tokens = cls._extract_int_value(
                token_usage,
                primary_key="completion_tokens",
                fallback_key="output_tokens",
            )
        if total_tokens == 0:
            total_tokens = cls._extract_int_value(
                token_usage,
                primary_key="total_tokens",
                fallback_key="total_tokens",
            )

        if total_tokens == 0 and (prompt_tokens or completion_tokens):
            total_tokens = prompt_tokens + completion_tokens

        if not any((prompt_tokens, completion_tokens, total_tokens)):
            return None

        return TokenUsage(
            prompt=prompt_tokens,
            completion=completion_tokens,
            total=total_tokens,
        )

    @classmethod
    def _extract_finish_reason(cls, model_output: Any) -> str | None:
        """Extract one normalized finish reason from a model end payload."""
        response_metadata = cls._extract_output_field(model_output, "response_metadata")
        return cls._normalize_optional_string(
            cls._extract_output_field(response_metadata, "finish_reason")
        )

    @staticmethod
    def _extract_output_field(payload: Any, field_name: str) -> Any:
        """Read one field from either dict or object payload shapes."""
        if payload is None:
            return None
        if isinstance(payload, dict):
            return payload.get(field_name)
        return getattr(payload, field_name, None)

    @classmethod
    def _extract_int_value(
        cls,
        payload: Any,
        *,
        primary_key: str,
        fallback_key: str,
    ) -> int:
        """Extract one integer value from a metadata payload."""
        for key in (primary_key, fallback_key):
            value = cls._extract_output_field(payload, key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return 0

    @classmethod
    def _extract_todo_snapshot(cls, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize persisted todo state into a stable full-snapshot payload."""
        todos = state.get("todos", [])
        if not isinstance(todos, list):
            return []

        normalized_todos: list[dict[str, Any]] = []
        for todo in todos:
            encoded_todo = jsonable_encoder(todo)
            if not isinstance(encoded_todo, dict):
                continue

            normalized_todo = {
                "content": cls._normalize_optional_string(encoded_todo.get("content"))
                or "",
                "status": cls._normalize_optional_string(encoded_todo.get("status"))
                or "pending",
            }
            normalized_todos.append(normalized_todo)

        return normalized_todos

    @classmethod
    def _build_plan_update_payload(
        cls,
        *,
        conversation_id: str,
        todos: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the full-snapshot socket payload for plan updates."""
        summary = {
            "total": len(todos),
            "completed": 0,
            "in_progress": 0,
            "pending": 0,
        }
        for todo in todos:
            status = cls._normalize_optional_string(todo.get("status")) or "pending"
            if status not in summary:
                continue
            summary[status] += 1

        return {
            "conversation_id": conversation_id,
            "todos": todos,
            "summary": summary,
        }

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
    def _message_content_to_stream_token(cls, message: Any) -> str:
        """Extract one streamed token while preserving model-emitted whitespace."""
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)

        return cls._stream_content_to_text(content)

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

    @classmethod
    def _stream_content_to_text(cls, content: Any) -> str:
        """Convert streamed model content into a token string without trimming."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            return "".join(cls._stream_content_to_text(item) for item in content)

        if isinstance(content, dict):
            if "text" in content and content["text"] is not None:
                return str(content["text"])
            if "content" in content:
                return cls._stream_content_to_text(content["content"])
            return ""

        if content is None:
            return ""

        text = getattr(content, "text", None)
        if isinstance(text, str):
            return text

        return str(content)
