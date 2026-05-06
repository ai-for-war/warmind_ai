from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

checkpointer_module = ModuleType("app.infrastructure.langgraph.checkpointer")
checkpointer_module.get_langgraph_checkpointer = lambda: object()
checkpointer_module.get_stock_agent_langgraph_checkpointer = lambda: object()
sys.modules.setdefault("app.infrastructure.langgraph.checkpointer", checkpointer_module)

socket_gateway_module = ModuleType("app.socket_gateway")
socket_gateway_module.gateway = SimpleNamespace(emit_to_user=None)
sys.modules.setdefault("app.socket_gateway", socket_gateway_module)

common_service_module = ModuleType("app.common.service")


def get_auth_service():
    raise RuntimeError("Auth service should be overridden in this test")


def get_chat_service():
    raise RuntimeError("Chat service should be overridden in this test")


def get_lead_agent_service():
    raise RuntimeError("Lead-agent service should be overridden in this test")


def get_lead_agent_skill_service():
    raise RuntimeError("Lead-agent skill service should be overridden in this test")


def get_stock_agent_service():
    raise RuntimeError("Stock-agent service should be overridden in this test")


def get_stock_agent_skill_service():
    raise RuntimeError("Stock-agent skill service should be overridden in this test")


common_service_module.get_auth_service = get_auth_service
common_service_module.get_chat_service = get_chat_service
common_service_module.get_lead_agent_service = get_lead_agent_service
common_service_module.get_lead_agent_skill_service = get_lead_agent_skill_service
common_service_module.get_stock_agent_service = get_stock_agent_service
common_service_module.get_stock_agent_skill_service = get_stock_agent_skill_service
sys.modules["app.common.service"] = common_service_module

from app.api.deps import (  # noqa: E402
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.ai import chat as chat_api  # noqa: E402
from app.api.v1.ai import lead_agent as lead_agent_api  # noqa: E402
from app.api.v1.ai import stock_agent as stock_agent_api  # noqa: E402
from app.api.v1.ai.chat import router as chat_router  # noqa: E402
from app.api.v1.ai.lead_agent import router as lead_agent_router  # noqa: E402
from app.api.v1.ai.stock_agent import router as stock_agent_router  # noqa: E402
from app.common.exceptions import AppException  # noqa: E402
from app.common.exceptions.ai_exceptions import (  # noqa: E402
    LeadAgentConversationNotFoundError,
    StockAgentConversationNotFoundError,
)
from app.common.service import (  # noqa: E402
    get_chat_service,
    get_lead_agent_service,
    get_lead_agent_skill_service,
    get_stock_agent_service,
    get_stock_agent_skill_service,
)
from app.domain.models.conversation import (  # noqa: E402
    Conversation,
    ConversationStatus,
)
from app.domain.models.lead_agent_skill import LeadAgentSkill  # noqa: E402
from app.domain.models.message import Message, MessageRole  # noqa: E402
from app.domain.models.stock_agent_conversation import (  # noqa: E402
    StockAgentConversation,
)
from app.domain.models.stock_agent_message import StockAgentMessage  # noqa: E402
from app.domain.models.user import User, UserRole  # noqa: E402
from app.domain.schemas.lead_agent import (  # noqa: E402
    LeadAgentSkillEnablementResponse,
    LeadAgentSkillListResponse,
    LeadAgentSkillResponse,
    LeadAgentToolListResponse,
)
from app.domain.schemas.stock_agent import (  # noqa: E402
    StockAgentSkillEnablementResponse,
    StockAgentSkillListResponse,
    StockAgentToolListResponse,
)


THREAD_ID = "11111111-1111-4111-8111-111111111111"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user() -> User:
    now = _now()
    return User(
        _id="user-1",
        email="user-1@example.com",
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
) -> Conversation:
    now = _now()
    return Conversation(
        _id=conversation_id,
        user_id="user-1",
        organization_id="org-1",
        title=title,
        status=ConversationStatus.ACTIVE,
        message_count=1,
        last_message_at=now,
        thread_id=thread_id,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _stock_conversation() -> StockAgentConversation:
    now = _now()
    return StockAgentConversation(
        _id="conv-stock-1",
        user_id="user-1",
        organization_id="org-1",
        title="Stock Conversation",
        status=ConversationStatus.ACTIVE,
        message_count=1,
        last_message_at=now,
        thread_id=THREAD_ID,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _message(
    *,
    message_id: str,
    conversation_id: str,
    role: MessageRole = MessageRole.USER,
) -> Message:
    return Message(
        _id=message_id,
        conversation_id=conversation_id,
        thread_id=THREAD_ID,
        role=role,
        content=f"{conversation_id} message",
        attachments=[],
        metadata=None,
        is_complete=True,
        created_at=_now(),
        deleted_at=None,
    )


class _FakeLeadAgentService:
    async def search_conversations(self, **_kwargs) -> SimpleNamespace:
        return SimpleNamespace(
            items=[
                _conversation(
                    conversation_id="conv-lead-1",
                    title="Lead Conversation",
                    thread_id=THREAD_ID,
                )
            ],
            total=1,
        )

    async def get_conversation_messages(self, *, conversation_id: str, **_kwargs):
        if conversation_id == "conv-stock-1":
            raise LeadAgentConversationNotFoundError()
        return [
            _message(
                message_id="msg-lead-1",
                conversation_id="conv-lead-1",
            )
        ]

    async def get_conversation_plan(self, *, conversation_id: str, **_kwargs):
        if conversation_id == "conv-stock-1":
            raise LeadAgentConversationNotFoundError()
        return {
            "conversation_id": conversation_id,
            "todos": [],
            "summary": {
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "pending": 0,
            },
        }


class _FakeStockAgentService:
    async def search_conversations(self, **_kwargs) -> SimpleNamespace:
        return SimpleNamespace(items=[_stock_conversation()], total=1)

    async def get_conversation_messages(self, *, conversation_id: str, **_kwargs):
        if conversation_id == "conv-lead-1":
            raise StockAgentConversationNotFoundError()
        return [
            StockAgentMessage.model_validate(
                _message(
                    message_id="msg-stock-1",
                    conversation_id="conv-stock-1",
                ).model_dump()
            )
        ]

    async def send_message(self, *, conversation_id: str | None = None, **_kwargs):
        if conversation_id == "conv-lead-1":
            raise StockAgentConversationNotFoundError()
        return "msg-stock-user", conversation_id or "conv-stock-1"

    async def get_conversation_plan(self, *, conversation_id: str, **_kwargs):
        if conversation_id == "conv-lead-1":
            raise StockAgentConversationNotFoundError()
        return {
            "conversation_id": conversation_id,
            "todos": [],
            "summary": {
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "pending": 0,
            },
        }

    def configure_runtime(self, **_kwargs) -> None:
        return None

    async def process_agent_response(self, **_kwargs) -> None:
        return None


class _FakeChatConversationService:
    async def get_user_conversation(
        self,
        *,
        conversation_id: str,
        has_thread_id: bool | None = None,
        **_kwargs,
    ):
        if conversation_id == "conv-stock-1":
            return None
        if has_thread_id is False:
            return _conversation(
                conversation_id="conv-chat-1",
                title="Legacy Chat",
                thread_id=None,
            )
        return None

    async def get_messages(self, *, conversation_id: str):
        return [
            _message(
                message_id="msg-chat-1",
                conversation_id=conversation_id,
            )
        ]


class _FakeChatService:
    def __init__(self) -> None:
        self.conversation_service = _FakeChatConversationService()

    async def search_conversations(self, **_kwargs):
        return SimpleNamespace(
            items=[
                _conversation(
                    conversation_id="conv-chat-1",
                    title="Legacy Chat",
                    thread_id=None,
                )
            ],
            total=1,
        )


class _FakeLeadAgentSkillService:
    async def list_tools(self):
        return LeadAgentToolListResponse(items=[])

    async def list_skills(self, **_kwargs):
        skill = LeadAgentSkill(
            _id="lead-skill-object",
            skill_id="lead-sales-skill",
            name="Lead Sales Skill",
            description="Lead-only skill",
            activation_prompt="Use lead context",
            allowed_tool_names=[],
            version="1.0.0",
            created_by="user-1",
            organization_id="org-1",
            created_at=_now(),
            updated_at=_now(),
        )
        return LeadAgentSkillListResponse(
            items=[
                LeadAgentSkillResponse(
                    skill_id=skill.skill_id,
                    name=skill.name,
                    description=skill.description,
                    activation_prompt=skill.activation_prompt,
                    allowed_tool_names=skill.allowed_tool_names,
                    version=skill.version,
                    is_enabled=True,
                    created_at=skill.created_at,
                    updated_at=skill.updated_at,
                )
            ],
            total=1,
            skip=0,
            limit=20,
        )

    async def enable_skill(self, **_kwargs):
        return LeadAgentSkillEnablementResponse(
            skill_id="lead-sales-skill",
            is_enabled=True,
        )


class _FakeStockAgentSkillService:
    async def list_tools(self):
        return StockAgentToolListResponse(items=[])

    async def list_skills(self, **_kwargs):
        return StockAgentSkillListResponse(items=[], total=0, skip=0, limit=20)

    async def enable_skill(self, **_kwargs):
        raise RuntimeError("Stock-agent should not enable lead-agent skills")


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(_request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.include_router(chat_router)
    app.include_router(lead_agent_router)
    app.include_router(stock_agent_router)
    app.dependency_overrides[get_current_active_user] = _user
    app.dependency_overrides[get_current_organization_context] = (
        lambda: OrganizationContext(organization_id="org-1")
    )
    app.dependency_overrides[get_chat_service] = _FakeChatService
    app.dependency_overrides[chat_api.get_chat_service] = _FakeChatService
    app.dependency_overrides[get_lead_agent_service] = _FakeLeadAgentService
    app.dependency_overrides[lead_agent_api.get_lead_agent_service] = (
        _FakeLeadAgentService
    )
    app.dependency_overrides[get_lead_agent_skill_service] = (
        _FakeLeadAgentSkillService
    )
    app.dependency_overrides[lead_agent_api.get_lead_agent_skill_service] = (
        _FakeLeadAgentSkillService
    )
    app.dependency_overrides[get_stock_agent_service] = _FakeStockAgentService
    app.dependency_overrides[stock_agent_api.get_stock_agent_service] = (
        _FakeStockAgentService
    )
    app.dependency_overrides[get_stock_agent_skill_service] = (
        _FakeStockAgentSkillService
    )
    app.dependency_overrides[stock_agent_api.get_stock_agent_skill_service] = (
        _FakeStockAgentSkillService
    )
    return app


@pytest.mark.asyncio
async def test_lead_agent_api_excludes_stock_agent_conversations_and_messages() -> None:
    app = _build_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        list_response = await client.get("/lead-agent/conversations")
        messages_response = await client.get(
            "/lead-agent/conversations/conv-stock-1/messages"
        )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [
        "conv-lead-1"
    ]
    assert "conv-stock-1" not in [
        item["id"] for item in list_response.json()["items"]
    ]
    assert messages_response.status_code == 404
    assert messages_response.json() == {"detail": "Lead-agent conversation not found"}


@pytest.mark.asyncio
async def test_legacy_chat_api_excludes_stock_agent_conversations_and_messages() -> None:
    app = _build_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        list_response = await client.get("/chat/conversations")
        messages_response = await client.get(
            "/chat/conversations/conv-stock-1/messages"
        )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [
        "conv-chat-1"
    ]
    assert "conv-stock-1" not in [
        item["id"] for item in list_response.json()["items"]
    ]
    assert messages_response.status_code == 404
    assert messages_response.json() == {"detail": "Conversation not found"}


@pytest.mark.asyncio
async def test_stock_agent_api_excludes_lead_agent_storage_and_skill_access() -> None:
    app = _build_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        lead_skills_response = await client.get("/lead-agent/skills")
        stock_skills_response = await client.get("/stock-agent/skills")
        stock_conversations_response = await client.get("/stock-agent/conversations")
        stock_messages_response = await client.get(
            "/stock-agent/conversations/conv-lead-1/messages"
        )
        stock_send_response = await client.post(
            "/stock-agent/messages",
            json={
                "conversation_id": "conv-lead-1",
                "content": "Should reject lead conversation",
                "provider": "openai",
                "model": "gpt-5.4",
            },
        )

    assert lead_skills_response.status_code == 200
    assert lead_skills_response.json()["items"][0]["skill_id"] == "lead-sales-skill"
    assert stock_skills_response.status_code == 200
    assert stock_skills_response.json() == {
        "items": [],
        "total": 0,
        "skip": 0,
        "limit": 20,
    }
    assert stock_conversations_response.status_code == 200
    assert [item["id"] for item in stock_conversations_response.json()["items"]] == [
        "conv-stock-1"
    ]
    assert "conv-lead-1" not in [
        item["id"] for item in stock_conversations_response.json()["items"]
    ]
    assert stock_messages_response.status_code == 404
    assert stock_messages_response.json() == {
        "detail": "Stock-agent conversation not found"
    }
    assert stock_send_response.status_code == 404
    assert stock_send_response.json() == {
        "detail": "Stock-agent conversation not found"
    }
