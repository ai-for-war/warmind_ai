from __future__ import annotations

import os
import sys
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

from app.common.event_socket import ChatEvents
from app.common.exceptions.ai_exceptions import (
    LeadAgentConversationNotFoundError,
)
from app.domain.models.conversation import Conversation, ConversationStatus
from app.domain.models.message import Message, MessageMetadata, MessageRole
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


class _FakeStreamingAgent:
    def __init__(self) -> None:
        self.state = {
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
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
        thread_id=THREAD_ID,
    )


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
    assert metadata.tool_calls is not None
    assert metadata.tool_calls[0].name == "search_docs"
    assert metadata.tool_calls[0].arguments == {"query": "recap"}
    assert service._agent.stream_payloads[0]["enabled_skill_ids"] == ["web-research"]


@pytest.mark.asyncio
async def test_process_agent_response_persists_skill_metadata_additively() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(
        conversation_service=conversation_service,
        skill_access_resolver=_skill_access_resolver(
            enabled_skill_ids=["web-research"]
        ),
    )
    service._agent = _FakeSkillStreamingAgent()

    conversation_service.get_user_conversation.return_value = _conversation(
        thread_id=THREAD_ID
    )
    conversation_service.get_message.return_value = _message(
        message_id="msg-user",
        role=MessageRole.USER,
        content="Need research",
        thread_id=THREAD_ID,
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
    assert metadata.tool_calls is not None
    completed_payload = emit_to_user.await_args_list[-1].kwargs["data"]["metadata"]
    assert completed_payload["skill_id"] == "web-research"
    assert completed_payload["skill_version"] == "2.1.0"
    assert completed_payload["loaded_skills"] == ["web-research"]


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
async def test_process_agent_response_emits_plan_updated_after_persisted_todo_change() -> None:
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
    assert (
        "Optimistic tool input that should not be emitted yet"
        not in str(plan_payload["todos"])
    )


@pytest.mark.asyncio
async def test_process_agent_response_skips_plan_updated_when_persisted_todos_do_not_change() -> None:
    conversation_service = _conversation_service()
    service = LeadAgentService(conversation_service=conversation_service)
    service._agent = _FakePlanStreamingAgent(
        initial_todos=[
            {"content": "Inspect request", "status": "in_progress"},
        ],
        persisted_todos_after_write=[
            {"content": "Inspect request", "status": "in_progress"},
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
    assert ChatEvents.MESSAGE_PLAN_UPDATED not in emitted_events


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
