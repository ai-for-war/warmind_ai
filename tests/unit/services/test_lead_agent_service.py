from __future__ import annotations

import os
import ssl
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("DEBUG", "false")

checkpointer_module = ModuleType("app.infrastructure.langgraph.checkpointer")
checkpointer_module.get_langgraph_checkpointer = lambda: object()
sys.modules.setdefault(
    "app.infrastructure.langgraph.checkpointer",
    checkpointer_module,
)
socket_gateway_module = ModuleType("app.socket_gateway")
socket_gateway_module.gateway = SimpleNamespace(emit_to_user=None)
sys.modules.setdefault("app.socket_gateway", socket_gateway_module)

from app.common.event_socket import ChatEvents
from app.common.exceptions.ai_exceptions import (
    LeadAgentConversationNotFoundError,
)
from app.domain.models.conversation import Conversation, ConversationStatus
from app.domain.models.message import Message, MessageMetadata, MessageRole, TokenUsage
from app.services.ai.lead_agent_service import LeadAgentService
import app.services.ai.lead_agent_service as lead_agent_service_module

THREAD_ID = "11111111-1111-4111-8111-111111111111"
OTHER_THREAD_ID = "22222222-2222-4222-8222-222222222222"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conversation(
    *,
    conversation_id: str = "conv-1",
    user_id: str = "user-1",
    organization_id: str = "org-1",
    title: str = "Lead Agent Conversation",
    thread_id: str | None = THREAD_ID,
) -> Conversation:
    now = _now()
    return Conversation(
        _id=conversation_id,
        user_id=user_id,
        organization_id=organization_id,
        title=title,
        status=ConversationStatus.ACTIVE,
        message_count=1,
        last_message_at=now,
        thread_id=thread_id,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _message(
    *,
    message_id: str = "msg-1",
    conversation_id: str = "conv-1",
    role: MessageRole = MessageRole.USER,
    content: str = "hello",
    thread_id: str | None = THREAD_ID,
    metadata: MessageMetadata | None = None,
) -> Message:
    return Message(
        _id=message_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        role=role,
        content=content,
        attachments=[],
        metadata=metadata,
        is_complete=True,
        created_at=_now(),
        deleted_at=None,
    )


def _conversation_service() -> SimpleNamespace:
    return SimpleNamespace(
        create_conversation=AsyncMock(),
        create_conversation_from_initial_message=AsyncMock(),
        add_message=AsyncMock(),
        get_user_conversation=AsyncMock(),
        get_message=AsyncMock(),
        get_messages=AsyncMock(),
        search_user_conversations=AsyncMock(),
    )


def _skill_access_resolver(
    *,
    enabled_skill_ids: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        resolve_for_caller=AsyncMock(
            return_value=SimpleNamespace(
                enabled_skill_ids=enabled_skill_ids or [],
            )
        )
    )


@dataclass
class _ToolInputWithRuntimeState:
    query: str
    transport: dict[str, object]


class _FakeStreamingAgent:
    def __init__(self) -> None:
        self.state = {
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
            "subagent_enabled": False,
            "orchestration_mode": "direct",
            "delegation_depth": 0,
            "delegation_parent_run_id": None,
            "delegated_execution_metadata": None,
        }
        self.stream_payloads: list[dict[str, object]] = []

    async def aget_state(self, _config: dict[str, dict[str, str]]):
        return SimpleNamespace(values=dict(self.state))

    async def astream_events(
        self,
        payload: dict[str, object],
        *,
        config: dict[str, dict[str, str]] | None = None,
        version: str | None = None,
    ):
        del config, version
        self.stream_payloads.append(dict(payload))
        self.state.update(
            {
                "messages": payload["messages"]
                + [{"role": "assistant", "content": "Final answer"}],
                "user_id": payload["user_id"],
                "organization_id": payload["organization_id"],
                "subagent_enabled": payload.get("subagent_enabled", False),
                "orchestration_mode": payload.get("orchestration_mode"),
                "delegation_depth": payload.get("delegation_depth"),
                "delegation_parent_run_id": payload.get(
                    "delegation_parent_run_id"
                ),
                "delegated_execution_metadata": payload.get(
                    "delegated_execution_metadata"
                ),
                "enabled_skill_ids": payload.get("enabled_skill_ids", []),
                "active_skill_id": payload.get("active_skill_id"),
                "allowed_tool_names": payload.get("allowed_tool_names", []),
                "active_skill_version": payload.get("active_skill_version"),
                "loaded_skills": payload.get("loaded_skills", []),
            }
        )
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="Final ")},
        }
        yield {
            "event": "on_tool_start",
            "name": "search_docs",
            "run_id": "tool-1",
            "data": {"input": {"query": "recap"}},
        }
        yield {
            "event": "on_tool_end",
            "run_id": "tool-1",
            "data": {"output": {"status": "ok"}},
        }
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="answer")},
        }
        yield {
            "event": "on_chat_model_end",
            "data": {
                "output": SimpleNamespace(
                    usage_metadata={
                        "input_tokens": 11,
                        "output_tokens": 7,
                        "total_tokens": 18,
                    },
                    response_metadata={"finish_reason": "stop"},
                )
            },
        }


class _FakeFailingAgent(_FakeStreamingAgent):
    async def astream_events(
        self,
        payload: dict[str, object],
        *,
        config: dict[str, dict[str, str]] | None = None,
        version: str | None = None,
    ):
        del payload, config, version
        if False:
            yield {}
        raise RuntimeError("runtime exploded")


class _FakeSkillStreamingAgent(_FakeStreamingAgent):
    async def astream_events(
        self,
        payload: dict[str, object],
        *,
        config: dict[str, dict[str, str]] | None = None,
        version: str | None = None,
    ):
        async for event in super().astream_events(
            payload,
            config=config,
            version=version,
        ):
            yield event

        self.state.update(
            {
                "active_skill_id": "web-research",
                "active_skill_version": "2.1.0",
                "loaded_skills": ["web-research"],
            }
        )


class _FakeToolErrorStreamingAgent(_FakeStreamingAgent):
    async def astream_events(
        self,
        payload: dict[str, object],
        *,
        config: dict[str, dict[str, str]] | None = None,
        version: str | None = None,
    ):
        del config, version
        self.stream_payloads.append(dict(payload))
        self.state.update(
            {
                "messages": payload["messages"]
                + [{"role": "assistant", "content": "Recovered answer"}],
                "user_id": payload["user_id"],
                "organization_id": payload["organization_id"],
                "subagent_enabled": payload.get("subagent_enabled", False),
                "orchestration_mode": payload.get("orchestration_mode"),
                "delegation_depth": payload.get("delegation_depth"),
                "delegation_parent_run_id": payload.get(
                    "delegation_parent_run_id"
                ),
                "delegated_execution_metadata": payload.get(
                    "delegated_execution_metadata"
                ),
                "enabled_skill_ids": payload.get("enabled_skill_ids", []),
                "active_skill_id": payload.get("active_skill_id"),
                "allowed_tool_names": payload.get("allowed_tool_names", []),
                "active_skill_version": payload.get("active_skill_version"),
                "loaded_skills": payload.get("loaded_skills", []),
            }
        )
        yield {
            "event": "on_tool_start",
            "name": "fetch_content",
            "run_id": "tool-error-1",
            "data": {"input": {"url": "https://example.com/missing"}},
        }
        yield {
            "event": "on_tool_error",
            "name": "fetch_content",
            "run_id": "tool-error-1",
            "data": {"error": RuntimeError("HTTP 404")},
        }
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="Recovered answer")},
        }
        yield {
            "event": "on_chat_model_end",
            "data": {
                "output": SimpleNamespace(
                    usage_metadata={
                        "input_tokens": 4,
                        "output_tokens": 2,
                        "total_tokens": 6,
                    },
                    response_metadata={"finish_reason": "stop"},
                )
            },
        }


class _FakePlanStreamingAgent(_FakeStreamingAgent):
    def __init__(
        self,
        *,
        initial_todos: list[dict[str, str]] | None = None,
        persisted_todos_after_write: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__()
        self.state["todos"] = list(initial_todos or [])
        self._persisted_todos_after_write = list(
            persisted_todos_after_write if persisted_todos_after_write is not None else []
        )

    async def astream_events(
        self,
        payload: dict[str, object],
        *,
        config: dict[str, dict[str, str]] | None = None,
        version: str | None = None,
    ):
        del config, version
        self.stream_payloads.append(dict(payload))
        self.state.update(
            {
                "messages": payload["messages"]
                + [{"role": "assistant", "content": "Planned answer"}],
                "user_id": payload["user_id"],
                "organization_id": payload["organization_id"],
                "subagent_enabled": payload.get("subagent_enabled", False),
                "orchestration_mode": payload.get("orchestration_mode"),
                "delegation_depth": payload.get("delegation_depth"),
                "delegation_parent_run_id": payload.get(
                    "delegation_parent_run_id"
                ),
                "delegated_execution_metadata": payload.get(
                    "delegated_execution_metadata"
                ),
            }
        )
        yield {
            "event": "on_tool_start",
            "name": "write_todos",
            "run_id": "tool-plan-1",
            "data": {
                "input": {
                    "todos": [
                        {
                            "content": "Optimistic tool input that should not be emitted yet",
                            "status": "in_progress",
                        }
                    ]
                }
            },
        }
        self.state["todos"] = list(self._persisted_todos_after_write)
        yield {
            "event": "on_tool_end",
            "run_id": "tool-plan-1",
            "data": {"output": {"status": "ok"}},
        }
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="Planned answer")},
        }


class _FakeDelegationStreamingAgent(_FakeStreamingAgent):
    async def astream_events(
        self,
        payload: dict[str, object],
        *,
        config: dict[str, dict[str, str]] | None = None,
        version: str | None = None,
    ):
        del config, version
        self.stream_payloads.append(dict(payload))
        self.state.update(
            {
                "messages": payload["messages"]
                + [{"role": "assistant", "content": "Final parent answer"}],
                "user_id": payload["user_id"],
                "organization_id": payload["organization_id"],
                "subagent_enabled": payload.get("subagent_enabled", False),
                "orchestration_mode": payload.get("orchestration_mode"),
                "delegation_depth": payload.get("delegation_depth"),
                "delegation_parent_run_id": payload.get(
                    "delegation_parent_run_id"
                ),
                "delegated_execution_metadata": payload.get(
                    "delegated_execution_metadata"
                ),
            }
        )
        yield {
            "event": "on_tool_start",
            "name": "delegate_tasks",
            "run_id": "delegate-1",
            "parent_ids": [],
            "data": {"input": {"task": {"objective": "Research site A"}}},
        }
        yield {
            "event": "on_chat_model_stream",
            "parent_ids": ["delegate-1"],
            "data": {"chunk": SimpleNamespace(content="Nested worker token")},
        }
        yield {
            "event": "on_tool_start",
            "name": "search",
            "run_id": "nested-tool-1",
            "parent_ids": ["delegate-1"],
            "data": {"input": {"query": "site:a.example"}},
        }
        yield {
            "event": "on_tool_end",
            "run_id": "nested-tool-1",
            "parent_ids": ["delegate-1"],
            "data": {"output": {"status": "ok"}},
        }
        yield {
            "event": "on_chat_model_end",
            "parent_ids": ["delegate-1"],
            "data": {
                "output": SimpleNamespace(
                    usage_metadata={
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "total_tokens": 150,
                    },
                    response_metadata={"finish_reason": "stop"},
                )
            },
        }
        yield {
            "event": "on_tool_end",
            "run_id": "delegate-1",
            "parent_ids": [],
            "data": {"output": {"status": "completed", "result": {"summary": "done"}}},
        }
        yield {
            "event": "on_chat_model_stream",
            "parent_ids": [],
            "data": {"chunk": SimpleNamespace(content="Final parent answer")},
        }
        yield {
            "event": "on_chat_model_end",
            "parent_ids": [],
            "data": {
                "output": SimpleNamespace(
                    usage_metadata={
                        "input_tokens": 11,
                        "output_tokens": 7,
                        "total_tokens": 18,
                    },
                    response_metadata={"finish_reason": "stop"},
                )
            },
        }


@pytest.mark.asyncio
async def test_create_thread_seeds_default_todos_revision() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    seeded_agent = SimpleNamespace(aupdate_state=AsyncMock())
    service._agent = seeded_agent

    thread_id = await service._create_thread(
        user_id="user-1",
        organization_id="org-1",
    )

    assert thread_id
    seeded_agent.aupdate_state.assert_awaited_once()
    update_call = seeded_agent.aupdate_state.await_args
    assert update_call.kwargs["values"]["todos_revision"] == 0


@pytest.mark.asyncio
async def test_send_message_creates_conversation_projection_and_thread() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    service._create_thread = AsyncMock(return_value=THREAD_ID)
    conversation_service.create_conversation_from_initial_message.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.add_message.return_value = _message(
        message_id="msg-user",
        thread_id=THREAD_ID,
        content="hello there",
    )

    user_message_id, conversation_id = await service.send_message(
        user_id="user-1",
        content=" hello there ",
        organization_id="org-1",
    )

    assert (user_message_id, conversation_id) == ("msg-user", "conv-1")
    service._create_thread.assert_awaited_once_with(
        user_id="user-1",
        organization_id="org-1",
    )
    conversation_service.create_conversation_from_initial_message.assert_awaited_once_with(
        user_id="user-1",
        content="hello there",
        organization_id="org-1",
        thread_id=THREAD_ID,
    )
    conversation_service.add_message.assert_awaited_once_with(
        conversation_id="conv-1",
        role=MessageRole.USER,
        content="hello there",
        organization_id="org-1",
        metadata=MessageMetadata(
            subagent_enabled=False,
            orchestration_mode="direct",
        ),
        thread_id=THREAD_ID,
    )


@pytest.mark.asyncio
async def test_send_message_reuses_stored_thread_for_follow_up_turns() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.add_message.return_value = _message(
        message_id="msg-follow-up",
        thread_id=THREAD_ID,
        content="follow-up",
    )
    service._get_thread_state = AsyncMock(
        return_value={
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
        }
    )

    user_message_id, conversation_id = await service.send_message(
        user_id="user-1",
        content="follow-up",
        conversation_id="conv-1",
        organization_id="org-1",
    )

    assert (user_message_id, conversation_id) == ("msg-follow-up", "conv-1")
    conversation_service.create_conversation_from_initial_message.assert_not_called()
    conversation_service.get_user_conversation.assert_awaited_once_with(
        conversation_id="conv-1",
        user_id="user-1",
        organization_id="org-1",
        has_thread_id=True,
    )
    service._get_thread_state.assert_awaited_once_with(THREAD_ID)
    conversation_service.add_message.assert_awaited_once_with(
        conversation_id="conv-1",
        role=MessageRole.USER,
        content="follow-up",
        organization_id="org-1",
        metadata=MessageMetadata(
            subagent_enabled=False,
            orchestration_mode="direct",
        ),
        thread_id=THREAD_ID,
    )


@pytest.mark.asyncio
async def test_send_message_persists_turn_scoped_subagent_request_metadata() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    service._create_thread = AsyncMock(return_value=THREAD_ID)
    conversation_service.create_conversation_from_initial_message.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.add_message.return_value = _message(
        message_id="msg-user",
        thread_id=THREAD_ID,
        content="research this",
    )

    await service.send_message(
        user_id="user-1",
        content="research this",
        organization_id="org-1",
        subagent_enabled=True,
    )

    assert conversation_service.add_message.await_args.kwargs["metadata"] == MessageMetadata(
        subagent_enabled=True,
        orchestration_mode="subagent",
    )


@pytest.mark.asyncio
async def test_build_runtime_payload_resets_active_skill_state_for_new_user_turn() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    service._get_thread_state = AsyncMock(
        return_value={
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
            "active_skill_id": "web-research",
            "active_skill_version": "2.1.0",
            "allowed_tool_names": ["search_docs"],
            "loaded_skills": ["web-research"],
        }
    )
    service._resolve_skill_access_for_turn = AsyncMock(
        return_value=SimpleNamespace(enabled_skill_ids=["web-research"])
    )

    payload = await service._build_runtime_payload(
        thread_id=THREAD_ID,
        user_id="user-1",
        content="Need research",
        organization_id="org-1",
        subagent_enabled=False,
    )

    assert payload["enabled_skill_ids"] == ["web-research"]
    assert payload["active_skill_id"] is None
    assert payload["active_skill_version"] is None
    assert payload["allowed_tool_names"] == []
    assert payload["loaded_skills"] == []
    assert payload["todos_revision"] == 0


def test_service_builds_distinct_agent_variants_for_direct_and_subagent_turns(
    monkeypatch,
) -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    created_agents: list[bool] = []

    def _fake_create_lead_agent(runtime_config=None, *, subagent_enabled=False):
        del runtime_config
        created_agents.append(subagent_enabled)
        return f"agent-{subagent_enabled}"

    monkeypatch.setattr(
        lead_agent_service_module,
        "create_lead_agent",
        _fake_create_lead_agent,
    )

    direct_agent = service._get_agent(subagent_enabled=False)
    subagent_agent = service._get_agent(subagent_enabled=True)
    cached_subagent_agent = service._get_agent(subagent_enabled=True)

    assert direct_agent == "agent-False"
    assert subagent_agent == "agent-True"
    assert cached_subagent_agent == "agent-True"
    assert created_agents == [False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("conversation", "state"),
    [
        (None, None),
        (_conversation(thread_id=None), None),
        (
            _conversation(thread_id=THREAD_ID),
            {"messages": [], "user_id": "other-user", "organization_id": "org-1"},
        ),
    ],
)
async def test_send_message_rejects_unknown_unauthorized_or_non_lead_agent_conversations(
    conversation: Conversation | None,
    state: dict[str, object] | None,
) -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    conversation_service.get_user_conversation.return_value = conversation
    service._get_thread_state = AsyncMock(return_value=state)

    with pytest.raises(LeadAgentConversationNotFoundError):
        await service.send_message(
            user_id="user-1",
            content="follow-up",
            conversation_id="conv-1",
            organization_id="org-1",
        )

    conversation_service.add_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_agent_response_emits_socket_lifecycle_and_persists_assistant_message(
) -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(
        conversation_service=conversation_service,
        skill_access_resolver=_skill_access_resolver(
            enabled_skill_ids=["web-research"]
        ),
    )
    service.runtime_config = lead_agent_service_module.LeadAgentRuntimeConfig(
        provider="openai",
        model="gpt-5.2",
        reasoning="medium",
    )
    service._agent = _FakeStreamingAgent()

    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.get_message.return_value = _message(
        message_id="msg-user",
        role=MessageRole.USER,
        content="Need help",
        thread_id=THREAD_ID,
        metadata=MessageMetadata(
            subagent_enabled=False,
            orchestration_mode="direct",
        ),
    )

    async def _persist_assistant(**kwargs):
        return _message(
            message_id="msg-assistant",
            role=MessageRole.ASSISTANT,
            content=kwargs["content"],
            conversation_id=kwargs["conversation_id"],
            thread_id=kwargs["thread_id"],
            metadata=kwargs["metadata"],
        )

    conversation_service.add_message.side_effect = _persist_assistant
    emit_to_user = AsyncMock()
    monkeypatch_target = lead_agent_service_module.gateway
    original_emit = monkeypatch_target.emit_to_user
    monkeypatch_target.emit_to_user = emit_to_user

    try:
        await service.process_agent_response(
            user_id="user-1",
            conversation_id="conv-1",
            user_message_id="msg-user",
            organization_id="org-1",
        )
    finally:
        monkeypatch_target.emit_to_user = original_emit

    emitted_events = [call.kwargs["event"] for call in emit_to_user.await_args_list]
    assert emitted_events == [
        ChatEvents.MESSAGE_STARTED,
        ChatEvents.MESSAGE_TOKEN,
        ChatEvents.MESSAGE_TOOL_START,
        ChatEvents.MESSAGE_TOOL_END,
        ChatEvents.MESSAGE_TOKEN,
        ChatEvents.MESSAGE_COMPLETED,
    ]

    assistant_call = conversation_service.add_message.await_args
    assert assistant_call.kwargs["role"] == MessageRole.ASSISTANT
    assert assistant_call.kwargs["content"] == "Final answer"
    assert assistant_call.kwargs["thread_id"] == THREAD_ID
    metadata = assistant_call.kwargs["metadata"]
    assert metadata is not None
    assert metadata.model == "gpt-5.2"
    assert metadata.tokens == TokenUsage(prompt=11, completion=7, total=18)
    assert metadata.finish_reason == "stop"
    assert metadata.tool_calls is not None
    assert metadata.tool_calls[0].name == "search_docs"
    assert metadata.tool_calls[0].arguments == {"query": "recap"}
    assert metadata.subagent_enabled is False
    assert metadata.orchestration_mode == "direct"
    assert metadata.delegation_depth == 0
    assert service._agent.stream_payloads[0]["enabled_skill_ids"] == ["web-research"]
    assert service._agent.stream_payloads[0]["subagent_enabled"] is False
    assert service._agent.stream_payloads[0]["orchestration_mode"] == "direct"
    completed_payload = emit_to_user.await_args_list[-1].kwargs["data"]["metadata"]
    assert completed_payload["tokens"] == {
        "prompt": 11,
        "completion": 7,
        "total": 18,
    }
    assert completed_payload["finish_reason"] == "stop"
    assert completed_payload["subagent_enabled"] is False
    assert completed_payload["orchestration_mode"] == "direct"
    assert completed_payload["delegation_depth"] == 0


@pytest.mark.asyncio
async def test_process_agent_response_persists_skill_metadata_additively() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(
        conversation_service=conversation_service,
        skill_access_resolver=_skill_access_resolver(
            enabled_skill_ids=["web-research"]
        ),
    )
    shared_agent = _FakeSkillStreamingAgent()
    service._agent = shared_agent
    service._subagent_agent = shared_agent

    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.get_message.return_value = _message(
        message_id="msg-user",
        role=MessageRole.USER,
        content="Need research",
        thread_id=THREAD_ID,
        metadata=MessageMetadata(
            subagent_enabled=True,
            orchestration_mode="subagent",
        ),
    )

    async def _persist_assistant(**kwargs):
        return _message(
            message_id="msg-assistant",
            role=MessageRole.ASSISTANT,
            content=kwargs["content"],
            conversation_id=kwargs["conversation_id"],
            thread_id=kwargs["thread_id"],
            metadata=kwargs["metadata"],
        )

    conversation_service.add_message.side_effect = _persist_assistant
    emit_to_user = AsyncMock()
    monkeypatch_target = lead_agent_service_module.gateway
    original_emit = monkeypatch_target.emit_to_user
    monkeypatch_target.emit_to_user = emit_to_user

    try:
        await service.process_agent_response(
            user_id="user-1",
            conversation_id="conv-1",
            user_message_id="msg-user",
            organization_id="org-1",
        )
    finally:
        monkeypatch_target.emit_to_user = original_emit

    assistant_call = conversation_service.add_message.await_args
    metadata = assistant_call.kwargs["metadata"]
    assert metadata is not None
    assert metadata.skill_id == "web-research"
    assert metadata.skill_version == "2.1.0"
    assert metadata.loaded_skills == ["web-research"]
    assert metadata.subagent_enabled is True
    assert metadata.orchestration_mode == "subagent"
    assert metadata.delegation_depth == 0
    assert metadata.tool_calls is not None
    assert shared_agent.stream_payloads[0]["subagent_enabled"] is True
    assert shared_agent.stream_payloads[0]["orchestration_mode"] == "subagent"
    completed_payload = emit_to_user.await_args_list[-1].kwargs["data"]["metadata"]
    assert completed_payload["skill_id"] == "web-research"
    assert completed_payload["skill_version"] == "2.1.0"
    assert completed_payload["loaded_skills"] == ["web-research"]
    assert completed_payload["subagent_enabled"] is True
    assert completed_payload["orchestration_mode"] == "subagent"
    assert completed_payload["delegation_depth"] == 0


@pytest.mark.asyncio
async def test_process_agent_response_ignores_nested_subagent_events_in_main_stream() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    shared_agent = _FakeDelegationStreamingAgent()
    service._agent = shared_agent
    service._subagent_agent = shared_agent
    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.get_message.return_value = _message(
        message_id="msg-user",
        role=MessageRole.USER,
        content="Need parallel research",
        thread_id=THREAD_ID,
        metadata=MessageMetadata(
            subagent_enabled=True,
            orchestration_mode="subagent",
        ),
    )

    async def _persist_assistant(**kwargs):
        return _message(
            message_id="msg-assistant",
            role=MessageRole.ASSISTANT,
            content=kwargs["content"],
            conversation_id=kwargs["conversation_id"],
            thread_id=kwargs["thread_id"],
            metadata=kwargs["metadata"],
        )

    conversation_service.add_message.side_effect = _persist_assistant
    emit_to_user = AsyncMock()
    monkeypatch_target = lead_agent_service_module.gateway
    original_emit = monkeypatch_target.emit_to_user
    monkeypatch_target.emit_to_user = emit_to_user

    try:
        await service.process_agent_response(
            user_id="user-1",
            conversation_id="conv-1",
            user_message_id="msg-user",
            organization_id="org-1",
        )
    finally:
        monkeypatch_target.emit_to_user = original_emit

    emitted_events = [call.kwargs["event"] for call in emit_to_user.await_args_list]
    assert emitted_events == [
        ChatEvents.MESSAGE_STARTED,
        ChatEvents.MESSAGE_TOOL_START,
        ChatEvents.MESSAGE_TOOL_END,
        ChatEvents.MESSAGE_TOKEN,
        ChatEvents.MESSAGE_COMPLETED,
    ]

    tool_start_payload = emit_to_user.await_args_list[1].kwargs["data"]
    assert tool_start_payload["tool_name"] == "delegate_tasks"
    assert tool_start_payload["tool_call_id"] == "delegate-1"

    token_payloads = [
        call.kwargs["data"]["token"]
        for call in emit_to_user.await_args_list
        if call.kwargs["event"] == ChatEvents.MESSAGE_TOKEN
    ]
    assert token_payloads == ["Final parent answer"]

    assistant_call = conversation_service.add_message.await_args
    metadata = assistant_call.kwargs["metadata"]
    assert metadata is not None
    assert metadata.tokens == TokenUsage(prompt=11, completion=7, total=18)
    assert metadata.tool_calls is not None
    assert [tool_call.name for tool_call in metadata.tool_calls] == ["delegate_tasks"]


@pytest.mark.asyncio
async def test_process_agent_response_emits_tool_end_for_tool_error_events() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    service._agent = _FakeToolErrorStreamingAgent()
    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.get_message.return_value = _message(
        message_id="msg-user",
        role=MessageRole.USER,
        content="Need a fallback",
        thread_id=THREAD_ID,
        metadata=MessageMetadata(
            subagent_enabled=False,
            orchestration_mode="direct",
        ),
    )

    async def _persist_assistant(**kwargs):
        return _message(
            message_id="msg-assistant",
            role=MessageRole.ASSISTANT,
            content=kwargs["content"],
            conversation_id=kwargs["conversation_id"],
            thread_id=kwargs["thread_id"],
            metadata=kwargs["metadata"],
        )

    conversation_service.add_message.side_effect = _persist_assistant
    emit_to_user = AsyncMock()
    monkeypatch_target = lead_agent_service_module.gateway
    original_emit = monkeypatch_target.emit_to_user
    monkeypatch_target.emit_to_user = emit_to_user

    try:
        await service.process_agent_response(
            user_id="user-1",
            conversation_id="conv-1",
            user_message_id="msg-user",
            organization_id="org-1",
        )
    finally:
        monkeypatch_target.emit_to_user = original_emit

    emitted_events = [call.kwargs["event"] for call in emit_to_user.await_args_list]
    assert emitted_events == [
        ChatEvents.MESSAGE_STARTED,
        ChatEvents.MESSAGE_TOOL_START,
        ChatEvents.MESSAGE_TOOL_END,
        ChatEvents.MESSAGE_TOKEN,
        ChatEvents.MESSAGE_COMPLETED,
    ]
    tool_end_payload = emit_to_user.await_args_list[2].kwargs["data"]
    assert tool_end_payload["tool_call_id"] == "tool-error-1"
    assert tool_end_payload["result"] == "HTTP 404"
    assert tool_end_payload["error"] == "HTTP 404"


@pytest.mark.asyncio
async def test_process_agent_response_emits_failed_event_when_runtime_breaks() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    service._agent = _FakeFailingAgent()
    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=OTHER_THREAD_ID
    )
    conversation_service.get_message.return_value = _message(
        message_id="msg-user",
        role=MessageRole.USER,
        content="Need help",
        thread_id=OTHER_THREAD_ID,
        metadata=MessageMetadata(
            subagent_enabled=False,
            orchestration_mode="direct",
        ),
    )
    emit_to_user = AsyncMock()
    monkeypatch_target = lead_agent_service_module.gateway
    original_emit = monkeypatch_target.emit_to_user
    monkeypatch_target.emit_to_user = emit_to_user

    try:
        await service.process_agent_response(
            user_id="user-1",
            conversation_id="conv-1",
            user_message_id="msg-user",
            organization_id="org-1",
        )
    finally:
        monkeypatch_target.emit_to_user = original_emit

    emitted_events = [call.kwargs["event"] for call in emit_to_user.await_args_list]
    assert emitted_events == [
        ChatEvents.MESSAGE_STARTED,
        ChatEvents.MESSAGE_FAILED,
    ]
    assert "runtime exploded" in emit_to_user.await_args_list[-1].kwargs["data"]["error"]
    conversation_service.add_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_agent_response_emits_plan_updated_after_write_todo_completion() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    service._agent = _FakePlanStreamingAgent(
        initial_todos=[],
        persisted_todos_after_write=[
            {"content": "Inspect request", "status": "completed"},
            {"content": "Draft response", "status": "in_progress"},
        ],
    )
    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.get_message.return_value = _message(
        message_id="msg-user",
        role=MessageRole.USER,
        content="Need a plan",
        thread_id=THREAD_ID,
        metadata=MessageMetadata(
            subagent_enabled=False,
            orchestration_mode="direct",
        ),
    )

    async def _persist_assistant(**kwargs):
        return _message(
            message_id="msg-assistant",
            role=MessageRole.ASSISTANT,
            content=kwargs["content"],
            conversation_id=kwargs["conversation_id"],
            thread_id=kwargs["thread_id"],
            metadata=kwargs["metadata"],
        )

    conversation_service.add_message.side_effect = _persist_assistant
    emit_to_user = AsyncMock()
    monkeypatch_target = lead_agent_service_module.gateway
    original_emit = monkeypatch_target.emit_to_user
    monkeypatch_target.emit_to_user = emit_to_user

    try:
        await service.process_agent_response(
            user_id="user-1",
            conversation_id="conv-1",
            user_message_id="msg-user",
            organization_id="org-1",
        )
    finally:
        monkeypatch_target.emit_to_user = original_emit

    emitted_events = [call.kwargs["event"] for call in emit_to_user.await_args_list]
    assert emitted_events == [
        ChatEvents.MESSAGE_STARTED,
        ChatEvents.MESSAGE_PLAN_UPDATED,
        ChatEvents.MESSAGE_TOKEN,
        ChatEvents.MESSAGE_COMPLETED,
    ]
    plan_payload = emit_to_user.await_args_list[1].kwargs["data"]
    assert plan_payload == {
        "conversation_id": "conv-1",
        "todos": [
            {
                "content": "Optimistic tool input that should not be emitted yet",
                "status": "in_progress",
            }
        ],
        "summary": {
            "total": 1,
            "completed": 0,
            "in_progress": 1,
            "pending": 0,
        },
    }


@pytest.mark.asyncio
async def test_process_agent_response_emits_plan_updated_even_when_snapshot_matches_previous_plan() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    service._agent = _FakePlanStreamingAgent(
        initial_todos=[
            {
                "content": "Optimistic tool input that should not be emitted yet",
                "status": "in_progress",
            },
        ],
        persisted_todos_after_write=[
            {
                "content": "Optimistic tool input that should not be emitted yet",
                "status": "in_progress",
            },
        ],
    )
    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.get_message.return_value = _message(
        message_id="msg-user",
        role=MessageRole.USER,
        content="Need a plan",
        thread_id=THREAD_ID,
        metadata=MessageMetadata(
            subagent_enabled=False,
            orchestration_mode="direct",
        ),
    )

    async def _persist_assistant(**kwargs):
        return _message(
            message_id="msg-assistant",
            role=MessageRole.ASSISTANT,
            content=kwargs["content"],
            conversation_id=kwargs["conversation_id"],
            thread_id=kwargs["thread_id"],
            metadata=kwargs["metadata"],
        )

    conversation_service.add_message.side_effect = _persist_assistant
    emit_to_user = AsyncMock()
    monkeypatch_target = lead_agent_service_module.gateway
    original_emit = monkeypatch_target.emit_to_user
    monkeypatch_target.emit_to_user = emit_to_user

    try:
        await service.process_agent_response(
            user_id="user-1",
            conversation_id="conv-1",
            user_message_id="msg-user",
            organization_id="org-1",
        )
    finally:
        monkeypatch_target.emit_to_user = original_emit

    emitted_events = [call.kwargs["event"] for call in emit_to_user.await_args_list]
    assert emitted_events == [
        ChatEvents.MESSAGE_STARTED,
        ChatEvents.MESSAGE_PLAN_UPDATED,
        ChatEvents.MESSAGE_TOKEN,
        ChatEvents.MESSAGE_COMPLETED,
    ]


@pytest.mark.asyncio
async def test_process_agent_response_preserves_leading_whitespace_in_streamed_tokens() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    service._agent = _FakeStreamingAgent()
    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.get_message.return_value = _message(
        message_id="msg-user",
        role=MessageRole.USER,
        content="Need help",
        thread_id=THREAD_ID,
        metadata=MessageMetadata(
            subagent_enabled=False,
            orchestration_mode="direct",
        ),
    )

    async def _persist_assistant(**kwargs):
        return _message(
            message_id="msg-assistant",
            role=MessageRole.ASSISTANT,
            content=kwargs["content"],
            conversation_id=kwargs["conversation_id"],
            thread_id=kwargs["thread_id"],
            metadata=kwargs["metadata"],
        )

    conversation_service.add_message.side_effect = _persist_assistant
    emit_to_user = AsyncMock()
    monkeypatch_target = lead_agent_service_module.gateway
    original_emit = monkeypatch_target.emit_to_user
    monkeypatch_target.emit_to_user = emit_to_user

    try:
        await service.process_agent_response(
            user_id="user-1",
            conversation_id="conv-1",
            user_message_id="msg-user",
            organization_id="org-1",
        )
    finally:
        monkeypatch_target.emit_to_user = original_emit

    token_payloads = [
        call.kwargs["data"]["token"]
        for call in emit_to_user.await_args_list
        if call.kwargs["event"] == ChatEvents.MESSAGE_TOKEN
    ]
    assert token_payloads == ["Final ", "answer"]


def test_message_content_to_stream_token_preserves_whitespace_for_structured_content() -> None:
    token = LeadAgentService._message_content_to_stream_token(
        {
            "content": [
                {"text": "EM"},
                {"text": " trong"},
                {"text": " lĩnh vực"},
            ]
        }
    )

    assert token == "EM trong lĩnh vực"


def test_serialize_tool_arguments_falls_back_for_non_json_runtime_objects() -> None:
    tool_input = _ToolInputWithRuntimeState(
        query="recap",
        transport={"ssl_context": ssl.create_default_context()},
    )

    serialized = LeadAgentService._serialize_tool_arguments(tool_input)

    assert serialized["query"] == "recap"
    assert isinstance(serialized["transport"], dict)
    assert isinstance(serialized["transport"]["ssl_context"], str)


def test_serialize_tool_arguments_filters_injected_runtime_argument() -> None:
    serialized = LeadAgentService._serialize_tool_arguments(
        {
            "url": "https://filum.ai/",
            "fmt": "text_markdown",
            "runtime": "ToolRuntime(...)",
        }
    )

    assert serialized == {
        "url": "https://filum.ai/",
        "fmt": "text_markdown",
    }


def test_extract_token_usage_falls_back_to_response_metadata_token_usage() -> None:
    usage = LeadAgentService._extract_token_usage(
        {
            "response_metadata": {
                "token_usage": {
                    "prompt_tokens": 13,
                    "completion_tokens": 5,
                    "total_tokens": 18,
                }
            }
        }
    )

    assert usage == TokenUsage(prompt=13, completion=5, total=18)


@pytest.mark.asyncio
async def test_get_conversation_plan_returns_latest_persisted_snapshot() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    service._get_thread_state = AsyncMock(
        return_value={
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
            "todos": [
                {"content": "Inspect request", "status": "completed"},
                {"content": "Draft response", "status": "in_progress"},
            ],
        }
    )

    plan = await service.get_conversation_plan(
        conversation_id="conv-1",
        user_id="user-1",
        organization_id="org-1",
    )

    assert plan == {
        "conversation_id": "conv-1",
        "todos": [
            {"content": "Inspect request", "status": "completed"},
            {"content": "Draft response", "status": "in_progress"},
        ],
        "summary": {
            "total": 2,
            "completed": 1,
            "in_progress": 1,
            "pending": 0,
        },
    }


@pytest.mark.asyncio
async def test_get_conversation_plan_returns_valid_empty_snapshot_when_no_todos_exist() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    service._get_thread_state = AsyncMock(
        return_value={
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
        }
    )

    plan = await service.get_conversation_plan(
        conversation_id="conv-1",
        user_id="user-1",
        organization_id="org-1",
    )

    assert plan == {
        "conversation_id": "conv-1",
        "todos": [],
        "summary": {
            "total": 0,
            "completed": 0,
            "in_progress": 0,
            "pending": 0,
        },
    }
