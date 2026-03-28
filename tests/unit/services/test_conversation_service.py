from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.models.conversation import Conversation, ConversationStatus
from app.domain.models.message import Message, MessageRole
from app.services.ai.conversation_service import (
    ConversationService,
    GeneratedConversationTitle,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conversation(title: str = "Quarterly planning recap") -> Conversation:
    now = _now()
    return Conversation(
        _id="conv-1",
        user_id="user-1",
        organization_id="org-1",
        title=title,
        status=ConversationStatus.ACTIVE,
        message_count=0,
        last_message_at=None,
        thread_id="thread-1",
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _message(content: str = "hello there") -> Message:
    return Message(
        _id="msg-1",
        conversation_id="conv-1",
        thread_id="thread-1",
        role=MessageRole.USER,
        content=content,
        attachments=[],
        metadata=None,
        is_complete=True,
        created_at=_now(),
        deleted_at=None,
    )


class _FakeStructuredLLM:
    def __init__(
        self,
        *,
        result: GeneratedConversationTitle | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error

    async def ainvoke(self, _messages):
        if self._error is not None:
            raise self._error
        return self._result


class _FakeLLM:
    def __init__(
        self,
        *,
        result: GeneratedConversationTitle | None = None,
        error: Exception | None = None,
    ) -> None:
        self._structured_llm = _FakeStructuredLLM(result=result, error=error)

    def with_structured_output(self, _schema):
        return self._structured_llm


@pytest.mark.asyncio
async def test_create_conversation_from_initial_message_uses_llm_title() -> None:
    conversation_repo = SimpleNamespace(
        create=AsyncMock(return_value=_conversation()),
        increment_message_count=AsyncMock(),
    )
    message_repo = SimpleNamespace(create=AsyncMock())
    service = ConversationService(
        conversation_repo,
        message_repo,
        llm_factory=lambda: _FakeLLM(
            result=GeneratedConversationTitle(title="Quarterly planning recap")
        ),
    )

    conversation = await service.create_conversation_from_initial_message(
        user_id="user-1",
        content="Help me plan the quarterly recap for the sales team",
        organization_id="org-1",
        thread_id="thread-1",
    )

    assert conversation.title == "Quarterly planning recap"
    conversation_repo.create.assert_awaited_once_with(
        user_id="user-1",
        title="Quarterly planning recap",
        organization_id="org-1",
        thread_id="thread-1",
    )


@pytest.mark.asyncio
async def test_generate_initial_title_falls_back_when_llm_fails() -> None:
    conversation_repo = SimpleNamespace(
        create=AsyncMock(),
        increment_message_count=AsyncMock(),
    )
    message_repo = SimpleNamespace(create=AsyncMock())
    service = ConversationService(
        conversation_repo,
        message_repo,
        llm_factory=lambda: _FakeLLM(error=RuntimeError("boom")),
    )
    content = "Need help building a quarterly planning recap workflow for sales"

    title = await service.generate_initial_title(content)

    assert title == service._generate_title_from_content(content)


@pytest.mark.asyncio
async def test_add_message_does_not_requery_title_for_user_messages() -> None:
    message = _message()
    conversation_repo = SimpleNamespace(
        increment_message_count=AsyncMock(return_value=_conversation()),
        get_by_id=AsyncMock(),
        update=AsyncMock(),
    )
    message_repo = SimpleNamespace(create=AsyncMock(return_value=message))
    service = ConversationService(
        conversation_repo,
        message_repo,
        llm_factory=lambda: _FakeLLM(
            result=GeneratedConversationTitle(title="unused")
        ),
    )

    persisted = await service.add_message(
        conversation_id="conv-1",
        role=MessageRole.USER,
        content="hello there",
        organization_id="org-1",
        thread_id="thread-1",
    )

    assert persisted.id == "msg-1"
    conversation_repo.increment_message_count.assert_awaited_once()
    conversation_repo.get_by_id.assert_not_awaited()
    conversation_repo.update.assert_not_awaited()
