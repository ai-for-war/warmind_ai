from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("DEBUG", "false")

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


class _FakeStreamingAgent:
    def __init__(self) -> None:
        self.state = {
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
        }

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
        self.state.update(
            {
                "messages": payload["messages"]
                + [{"role": "assistant", "content": "Final answer"}],
                "user_id": payload["user_id"],
                "organization_id": payload["organization_id"],
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
    assert metadata.tool_calls is not None
    assert metadata.tool_calls[0].name == "search_docs"
    assert metadata.tool_calls[0].arguments == {"query": "recap"}


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
