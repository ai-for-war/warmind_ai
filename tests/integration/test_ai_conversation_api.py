from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Iterable
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DEBUG", "false")

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.ai.chat import router as chat_router
from app.api.v1.ai.lead_agent import router as lead_agent_router
from app.common.exceptions import AppException
from app.common.service import get_chat_service, get_lead_agent_service
from app.common.exceptions.ai_exceptions import LeadAgentConversationNotFoundError
from app.domain.models.conversation import Conversation, ConversationStatus
from app.domain.models.message import Message, MessageRole
from app.domain.models.user import User, UserRole
from app.repo.conversation_repo import SearchResult
from app.services.ai.chat_service import ChatService
from app.services.ai.lead_agent_service import LeadAgentService

THREAD_ID = "11111111-1111-4111-8111-111111111111"


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _user(*, user_id: str = "user-1") -> User:
    now = _utc(2026, 1, 1)
    return User(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _conversation(
    *,
    conversation_id: str,
    title: str,
    thread_id: str | None,
    user_id: str = "user-1",
    organization_id: str = "org-1",
    updated_at: datetime | None = None,
) -> Conversation:
    now = updated_at or _utc(2026, 1, 2)
    return Conversation(
        _id=conversation_id,
        user_id=user_id,
        organization_id=organization_id,
        title=title,
        status=ConversationStatus.ACTIVE,
        message_count=2,
        last_message_at=now,
        thread_id=thread_id,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _message(
    *,
    message_id: str,
    conversation_id: str,
    role: MessageRole,
    content: str,
    created_at: datetime,
    thread_id: str | None,
) -> Message:
    return Message(
        _id=message_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        role=role,
        content=content,
        attachments=[],
        metadata=None,
        is_complete=True,
        created_at=created_at,
        deleted_at=None,
    )


class _InMemoryConversationService:
    def __init__(
        self,
        *,
        conversations: Iterable[Conversation],
        messages: Iterable[Message],
    ) -> None:
        self._conversations = list(conversations)
        self._messages_by_conversation: dict[str, list[Message]] = defaultdict(list)
        for message in messages:
            self._messages_by_conversation[message.conversation_id].append(message)

    @staticmethod
    def _matches_runtime_class(
        conversation: Conversation,
        has_thread_id: bool | None,
    ) -> bool:
        if has_thread_id is None:
            return True
        return (conversation.thread_id is not None) is has_thread_id

    async def search_user_conversations(
        self,
        *,
        user_id: str,
        organization_id: str | None = None,
        has_thread_id: bool | None = None,
        status: ConversationStatus | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> SearchResult:
        items = [
            conversation
            for conversation in self._conversations
            if conversation.user_id == user_id
            and conversation.organization_id == organization_id
            and self._matches_runtime_class(conversation, has_thread_id)
        ]
        if status is not None:
            items = [item for item in items if item.status == status.value]
        if search:
            items = [item for item in items if search.lower() in item.title.lower()]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        paginated = items[skip : skip + limit]
        return SearchResult(items=paginated, total=len(items))

    async def get_user_conversation(
        self,
        conversation_id: str,
        user_id: str,
        organization_id: str | None = None,
        has_thread_id: bool | None = None,
    ) -> Conversation | None:
        for conversation in self._conversations:
            if conversation.id != conversation_id:
                continue
            if conversation.user_id != user_id:
                continue
            if conversation.organization_id != organization_id:
                continue
            if not self._matches_runtime_class(conversation, has_thread_id):
                return None
            return conversation
        return None

    async def get_messages(
        self,
        *,
        conversation_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Message]:
        messages = sorted(
            self._messages_by_conversation.get(conversation_id, []),
            key=lambda message: message.created_at,
        )
        return messages[skip : skip + limit]


def _build_test_app(
    *,
    chat_service: ChatService,
    lead_agent_service: LeadAgentService,
) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(_request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.include_router(chat_router)
    app.include_router(lead_agent_router)
    app.dependency_overrides[get_current_active_user] = lambda: _user()
    app.dependency_overrides[get_current_organization_context] = (
        lambda: OrganizationContext(organization_id="org-1")
    )
    app.dependency_overrides[get_chat_service] = lambda: chat_service
    app.dependency_overrides[get_lead_agent_service] = lambda: lead_agent_service
    return app


@pytest.mark.asyncio
async def test_lead_agent_endpoints_return_thread_backed_conversations_and_ordered_history() -> None:
    legacy_conversation = _conversation(
        conversation_id="conv-chat",
        title="Legacy chat",
        thread_id=None,
        updated_at=_utc(2026, 1, 2, 9),
    )
    lead_conversation = _conversation(
        conversation_id="conv-lead",
        title="Lead planning",
        thread_id=THREAD_ID,
        updated_at=_utc(2026, 1, 2, 10),
    )
    conversation_service = _InMemoryConversationService(
        conversations=[legacy_conversation, lead_conversation],
        messages=[
            _message(
                message_id="assistant-late",
                conversation_id="conv-lead",
                role=MessageRole.ASSISTANT,
                content="Response",
                created_at=_utc(2026, 1, 2, 10, 2),
                thread_id=THREAD_ID,
            ),
            _message(
                message_id="user-early",
                conversation_id="conv-lead",
                role=MessageRole.USER,
                content="Question",
                created_at=_utc(2026, 1, 2, 10, 1),
                thread_id=THREAD_ID,
            ),
        ],
    )
    app = _build_test_app(
        chat_service=ChatService(
            conversation_service=conversation_service,
            data_query_service=AsyncMock(),
        ),
        lead_agent_service=SimpleNamespace(
            search_conversations=AsyncMock(
                return_value=SearchResult(items=[lead_conversation], total=1)
            ),
            get_conversation_messages=AsyncMock(
                return_value=sorted(
                    conversation_service._messages_by_conversation["conv-lead"],
                    key=lambda message: message.created_at,
                )
            ),
            get_conversation_plan=AsyncMock(
                return_value={
                    "conversation_id": "conv-lead",
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
            ),
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        list_response = await client.get("/lead-agent/conversations")
        history_response = await client.get("/lead-agent/conversations/conv-lead/messages")
        plan_response = await client.get("/lead-agent/conversations/conv-lead/plan")

    assert list_response.status_code == 200
    assert list_response.json() == {
        "items": [
            {
                "id": "conv-lead",
                "title": "Lead planning",
                "status": "active",
                "message_count": 2,
                "last_message_at": _iso(lead_conversation.last_message_at),
                "created_at": _iso(lead_conversation.created_at),
                "updated_at": _iso(lead_conversation.updated_at),
                "thread_id": THREAD_ID,
            }
        ],
        "total": 1,
        "skip": 0,
        "limit": 20,
    }

    assert history_response.status_code == 200
    assert [message["id"] for message in history_response.json()["messages"]] == [
        "user-early",
        "assistant-late",
    ]
    assert all(
        message["thread_id"] == THREAD_ID
        for message in history_response.json()["messages"]
    )
    assert plan_response.status_code == 200
    assert plan_response.json() == {
        "conversation_id": "conv-lead",
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
async def test_lead_agent_catalog_endpoint_returns_provider_model_reasoning_matrix(
    monkeypatch,
) -> None:
    import app.api.v1.ai.lead_agent as lead_agent_api

    monkeypatch.setattr(
        lead_agent_api,
        "get_default_lead_agent_runtime_config",
        lambda: SimpleNamespace(
            provider="openai",
            model="gpt-5.2",
            reasoning="high",
        ),
    )
    monkeypatch.setattr(
        lead_agent_api,
        "get_lead_agent_runtime_catalog",
        lambda: (
            SimpleNamespace(
                provider="openai",
                display_name="OpenAI",
                is_default=True,
                models=(
                    SimpleNamespace(
                        model="gpt-5.2",
                        reasoning_options=("low", "medium", "high"),
                        default_reasoning="high",
                        is_default=True,
                    ),
                    SimpleNamespace(
                        model="gpt-4.1",
                        reasoning_options=(),
                        default_reasoning=None,
                        is_default=False,
                    ),
                ),
            ),
        ),
    )
    app = _build_test_app(
        chat_service=ChatService(
            conversation_service=_InMemoryConversationService(conversations=[], messages=[]),
            data_query_service=AsyncMock(),
        ),
        lead_agent_service=SimpleNamespace(),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/lead-agent/catalog")

    assert response.status_code == 200
    assert response.json() == {
        "default_provider": "openai",
        "default_model": "gpt-5.2",
        "default_reasoning": "high",
        "providers": [
            {
                "provider": "openai",
                "display_name": "OpenAI",
                "is_default": True,
                "models": [
                    {
                        "model": "gpt-5.2",
                        "reasoning_options": ["low", "medium", "high"],
                        "default_reasoning": "high",
                        "is_default": True,
                    },
                    {
                        "model": "gpt-4.1",
                        "reasoning_options": [],
                        "default_reasoning": None,
                        "is_default": False,
                    },
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_lead_agent_send_message_accepts_runtime_overrides() -> None:
    configured_runtime: dict[str, str | None] = {}

    def _configure_runtime(**kwargs):
        configured_runtime.update(kwargs)
        return kwargs

    lead_agent_service = SimpleNamespace(
        configure_runtime=_configure_runtime,
        send_message=AsyncMock(return_value=("msg-user", "conv-lead")),
        process_agent_response=AsyncMock(),
        search_conversations=AsyncMock(),
        get_conversation_messages=AsyncMock(),
        get_conversation_plan=AsyncMock(),
    )
    app = _build_test_app(
        chat_service=ChatService(
            conversation_service=_InMemoryConversationService(conversations=[], messages=[]),
            data_query_service=AsyncMock(),
        ),
        lead_agent_service=lead_agent_service,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/lead-agent/messages",
            json={
                "content": "Plan this",
                "provider": "openai",
                "model": "gpt-5.2",
                "reasoning": "medium",
                "subagent_enabled": True,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_message_id": "msg-user",
        "conversation_id": "conv-lead",
    }
    assert configured_runtime == {
        "provider": "openai",
        "model": "gpt-5.2",
        "reasoning": "medium",
    }
    assert lead_agent_service.send_message.await_args.kwargs == {
        "user_id": "user-1",
        "content": "Plan this",
        "conversation_id": None,
        "organization_id": "org-1",
        "subagent_enabled": True,
    }
    assert lead_agent_service.process_agent_response.await_args.kwargs == {
        "user_id": "user-1",
        "conversation_id": "conv-lead",
        "user_message_id": "msg-user",
        "organization_id": "org-1",
    }


@pytest.mark.asyncio
async def test_lead_agent_send_message_requires_provider_and_model() -> None:
    lead_agent_service = SimpleNamespace(
        configure_runtime=lambda **kwargs: kwargs,
        send_message=AsyncMock(),
        process_agent_response=AsyncMock(),
        search_conversations=AsyncMock(),
        get_conversation_messages=AsyncMock(),
        get_conversation_plan=AsyncMock(),
    )
    app = _build_test_app(
        chat_service=ChatService(
            conversation_service=_InMemoryConversationService(conversations=[], messages=[]),
            data_query_service=AsyncMock(),
        ),
        lead_agent_service=lead_agent_service,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        missing_provider_response = await client.post(
            "/lead-agent/messages",
            json={
                "content": "Plan this",
                "model": "gpt-5.2",
                "reasoning": "medium",
            },
        )
        missing_model_response = await client.post(
            "/lead-agent/messages",
            json={
                "content": "Plan this",
                "provider": "openai",
                "reasoning": "medium",
            },
        )

    assert missing_provider_response.status_code == 422
    assert missing_model_response.status_code == 422
    lead_agent_service.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_endpoints_exclude_lead_agent_projection_records() -> None:
    legacy_conversation = _conversation(
        conversation_id="conv-chat",
        title="Legacy chat",
        thread_id=None,
        updated_at=_utc(2026, 1, 2, 11),
    )
    lead_conversation = _conversation(
        conversation_id="conv-lead",
        title="Lead planning",
        thread_id=THREAD_ID,
        updated_at=_utc(2026, 1, 2, 12),
    )
    conversation_service = _InMemoryConversationService(
        conversations=[lead_conversation, legacy_conversation],
        messages=[
            _message(
                message_id="chat-user",
                conversation_id="conv-chat",
                role=MessageRole.USER,
                content="hello",
                created_at=_utc(2026, 1, 2, 11, 0),
                thread_id=None,
            ),
            _message(
                message_id="lead-user",
                conversation_id="conv-lead",
                role=MessageRole.USER,
                content="plan",
                created_at=_utc(2026, 1, 2, 12, 0),
                thread_id=THREAD_ID,
            ),
        ],
    )
    app = _build_test_app(
        chat_service=ChatService(
            conversation_service=conversation_service,
            data_query_service=AsyncMock(),
        ),
        lead_agent_service=LeadAgentService(conversation_service=conversation_service),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        list_response = await client.get("/chat/conversations")
        legacy_history = await client.get("/chat/conversations/conv-chat/messages")
        lead_history = await client.get("/chat/conversations/conv-lead/messages")

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == ["conv-chat"]

    assert legacy_history.status_code == 200
    assert legacy_history.json()["conversation_id"] == "conv-chat"
    assert legacy_history.json()["messages"][0]["thread_id"] is None

    assert lead_history.status_code == 404
    assert lead_history.json() == {"detail": "Conversation not found"}


@pytest.mark.asyncio
async def test_lead_agent_plan_endpoint_returns_empty_snapshot_and_not_found_for_cross_scope() -> None:
    lead_service = SimpleNamespace(
        search_conversations=AsyncMock(),
        get_conversation_messages=AsyncMock(),
        get_conversation_plan=AsyncMock(
            side_effect=[
                {
                    "conversation_id": "conv-lead",
                    "todos": [],
                    "summary": {
                        "total": 0,
                        "completed": 0,
                        "in_progress": 0,
                        "pending": 0,
                    },
                },
                LeadAgentConversationNotFoundError(),
            ]
        ),
    )
    app = _build_test_app(
        chat_service=ChatService(
            conversation_service=_InMemoryConversationService(conversations=[], messages=[]),
            data_query_service=AsyncMock(),
        ),
        lead_agent_service=lead_service,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        empty_plan_response = await client.get("/lead-agent/conversations/conv-lead/plan")
        missing_plan_response = await client.get("/lead-agent/conversations/conv-missing/plan")

    assert empty_plan_response.status_code == 200
    assert empty_plan_response.json() == {
        "conversation_id": "conv-lead",
        "todos": [],
        "summary": {
            "total": 0,
            "completed": 0,
            "in_progress": 0,
            "pending": 0,
        },
    }
    assert missing_plan_response.status_code == 404
    assert missing_plan_response.json() == {
        "detail": "Lead-agent conversation not found"
    }
