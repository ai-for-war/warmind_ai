from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import ModuleType
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

cloudinary_module = ModuleType("cloudinary")
cloudinary_module.config = lambda **_kwargs: None
cloudinary_uploader_module = ModuleType("cloudinary.uploader")
cloudinary_uploader_module.upload = lambda *_args, **_kwargs: {}
cloudinary_uploader_module.destroy = lambda *_args, **_kwargs: {}
cloudinary_utils_module = ModuleType("cloudinary.utils")
cloudinary_utils_module.cloudinary_url = lambda *_args, **_kwargs: ("", {})
cloudinary_module.uploader = cloudinary_uploader_module
sys.modules.setdefault("cloudinary", cloudinary_module)
sys.modules.setdefault("cloudinary.uploader", cloudinary_uploader_module)
sys.modules.setdefault("cloudinary.utils", cloudinary_utils_module)

deepgram_module = ModuleType("deepgram")
deepgram_module.AsyncDeepgramClient = object
deepgram_core_events_module = ModuleType("deepgram.core.events")
deepgram_core_events_module.EventType = object
deepgram_close_module = ModuleType(
    "deepgram.listen.v1.types.listen_v1close_stream"
)
deepgram_close_module.ListenV1CloseStream = object
deepgram_finalize_module = ModuleType("deepgram.listen.v1.types.listen_v1finalize")
deepgram_finalize_module.ListenV1Finalize = object
deepgram_keep_alive_module = ModuleType(
    "deepgram.listen.v1.types.listen_v1keep_alive"
)
deepgram_keep_alive_module.ListenV1KeepAlive = object
sys.modules.setdefault("deepgram", deepgram_module)
sys.modules.setdefault("deepgram.core.events", deepgram_core_events_module)
sys.modules.setdefault(
    "deepgram.listen.v1.types.listen_v1close_stream",
    deepgram_close_module,
)
sys.modules.setdefault(
    "deepgram.listen.v1.types.listen_v1finalize",
    deepgram_finalize_module,
)
sys.modules.setdefault(
    "deepgram.listen.v1.types.listen_v1keep_alive",
    deepgram_keep_alive_module,
)

checkpointer_module = ModuleType("app.infrastructure.langgraph.checkpointer")
checkpointer_module.get_langgraph_checkpointer = lambda: object()
checkpointer_module.get_stock_agent_langgraph_checkpointer = lambda: object()
sys.modules.setdefault("app.infrastructure.langgraph.checkpointer", checkpointer_module)

common_service_module = ModuleType("app.common.service")


def get_auth_service():
    raise RuntimeError("Auth service should be overridden in this test")


def get_stock_agent_skill_service():
    raise RuntimeError("Stock-agent skill service should be overridden in this test")


def get_stock_agent_service():
    raise RuntimeError("Stock-agent service should be overridden in this test")


common_service_module.get_auth_service = get_auth_service
common_service_module.get_stock_agent_skill_service = get_stock_agent_skill_service
common_service_module.get_stock_agent_service = get_stock_agent_service
sys.modules["app.common.service"] = common_service_module

from app.agents.implementations.stock_agent.tool_catalog import (
    StockAgentSelectableToolDescriptor,
)
from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.ai.stock_agent import router as stock_agent_router
from app.common.exceptions.ai_exceptions import StockAgentConversationNotFoundError
from app.common.exceptions import AppException
from app.common.service import get_stock_agent_service, get_stock_agent_skill_service
from app.domain.models.conversation import ConversationStatus
from app.domain.models.message import MessageMetadata, MessageRole
from app.domain.models.stock_agent_conversation import StockAgentConversation
from app.domain.models.stock_agent_message import StockAgentMessage
from app.domain.models.stock_agent_skill import StockAgentSkill
from app.domain.models.stock_agent_skill_access import StockAgentSkillAccess
from app.domain.models.user import User, UserRole
from app.repo.stock_agent_skill_repo import StockAgentSkillListResult
from app.services.ai.stock_agent_skill_service import StockAgentSkillService


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _user() -> User:
    now = _utc(2026, 1, 1)
    return User(
        _id="user-1",
        email="user-1@example.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _InMemorySkillRepo:
    def __init__(self) -> None:
        self.skills: dict[tuple[str, str, str], StockAgentSkill] = {}
        self._counter = 0

    async def list_by_creator(
        self,
        *,
        user_id: str,
        organization_id: str,
        search: str | None = None,
        include_skill_ids: list[str] | None = None,
        exclude_skill_ids: list[str] | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> StockAgentSkillListResult:
        items = [
            skill
            for (created_by, org_id, _skill_id), skill in self.skills.items()
            if created_by == user_id and org_id == organization_id
        ]
        if search is not None and search.strip():
            normalized_search = search.strip().lower()
            items = [
                skill for skill in items if normalized_search in skill.name.lower()
            ]
        if include_skill_ids:
            include_skill_id_set = {skill_id.strip() for skill_id in include_skill_ids}
            items = [
                skill for skill in items if skill.skill_id in include_skill_id_set
            ]
        if exclude_skill_ids:
            exclude_skill_id_set = {skill_id.strip() for skill_id in exclude_skill_ids}
            items = [
                skill for skill in items if skill.skill_id not in exclude_skill_id_set
            ]
        items.sort(key=lambda skill: skill.updated_at, reverse=True)
        return StockAgentSkillListResult(items=items[skip : skip + limit], total=len(items))

    async def create(
        self,
        *,
        skill_id: str,
        name: str,
        description: str,
        activation_prompt: str,
        allowed_tool_names: list[str],
        version: str,
        created_by: str,
        organization_id: str,
    ) -> StockAgentSkill:
        self._counter += 1
        now = _now()
        skill = StockAgentSkill(
            _id=f"skill-{self._counter}",
            skill_id=skill_id,
            name=name,
            description=description,
            activation_prompt=activation_prompt,
            allowed_tool_names=list(allowed_tool_names),
            version=version,
            created_by=created_by,
            organization_id=organization_id,
            created_at=now,
            updated_at=now,
        )
        self.skills[(created_by, organization_id, skill_id)] = skill
        return skill

    async def get_by_creator_and_skill_id(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> StockAgentSkill | None:
        return self.skills.get((user_id, organization_id, skill_id))

    async def update_by_creator_and_skill_id(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        activation_prompt: str | None = None,
        allowed_tool_names: list[str] | None = None,
        version: str | None = None,
    ) -> StockAgentSkill | None:
        skill = self.skills.get((user_id, organization_id, skill_id))
        if skill is None:
            return None

        updated = skill.model_copy(
            update={
                "name": name if name is not None else skill.name,
                "description": description if description is not None else skill.description,
                "activation_prompt": (
                    activation_prompt
                    if activation_prompt is not None
                    else skill.activation_prompt
                ),
                "allowed_tool_names": (
                    list(allowed_tool_names)
                    if allowed_tool_names is not None
                    else skill.allowed_tool_names
                ),
                "version": version if version is not None else skill.version,
                "updated_at": _now(),
            }
        )
        self.skills[(user_id, organization_id, skill_id)] = updated
        return updated

    async def delete_by_creator_and_skill_id(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> bool:
        return self.skills.pop((user_id, organization_id, skill_id), None) is not None

    async def exists_by_creator_and_skill_id(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> bool:
        return (user_id, organization_id, skill_id) in self.skills


class _InMemoryAccessRepo:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], StockAgentSkillAccess] = {}
        self._counter = 0

    async def get_by_scope(
        self,
        user_id: str,
        organization_id: str,
    ) -> StockAgentSkillAccess | None:
        return self.records.get((user_id, organization_id))

    async def upsert_enabled_skills(
        self,
        user_id: str,
        enabled_skill_ids: list[str],
        organization_id: str,
    ) -> StockAgentSkillAccess:
        self._counter += 1
        now = _now()
        existing = self.records.get((user_id, organization_id))
        record = StockAgentSkillAccess(
            _id=existing.id if existing is not None else f"access-{self._counter}",
            user_id=user_id,
            organization_id=organization_id,
            enabled_skill_ids=list(enabled_skill_ids),
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        self.records[(user_id, organization_id)] = record
        return record


def _conversation(
    *,
    conversation_id: str = "conv-stock-1",
    thread_id: str = "11111111-1111-4111-8111-111111111111",
) -> StockAgentConversation:
    now = _now()
    return StockAgentConversation(
        _id=conversation_id,
        user_id="user-1",
        organization_id="org-1",
        title="Stock Agent Conversation",
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
    message_id: str = "msg-stock-1",
    role: MessageRole = MessageRole.USER,
    content: str = "Analyze VNM",
    thread_id: str = "11111111-1111-4111-8111-111111111111",
) -> StockAgentMessage:
    return StockAgentMessage(
        _id=message_id,
        conversation_id="conv-stock-1",
        thread_id=thread_id,
        role=role,
        content=content,
        attachments=[],
        metadata=MessageMetadata(model="gpt-5.4") if role == MessageRole.ASSISTANT else None,
        is_complete=True,
        created_at=_now(),
        deleted_at=None,
    )


class _FakeStockAgentService:
    def __init__(self) -> None:
        self.runtime_config_calls: list[dict[str, str | None]] = []
        self.send_message_calls: list[dict[str, object]] = []
        self.process_calls: list[dict[str, object]] = []

    def configure_runtime(
        self,
        *,
        provider: str,
        model: str,
        reasoning: str | None = None,
    ) -> None:
        self.runtime_config_calls.append(
            {
                "provider": provider,
                "model": model,
                "reasoning": reasoning,
            }
        )

    async def send_message(
        self,
        *,
        user_id: str,
        content: str,
        conversation_id: str | None = None,
        organization_id: str | None = None,
        subagent_enabled: bool = False,
    ) -> tuple[str, str]:
        if conversation_id == "lead-conversation-id":
            raise StockAgentConversationNotFoundError()

        self.send_message_calls.append(
            {
                "user_id": user_id,
                "content": content,
                "conversation_id": conversation_id,
                "organization_id": organization_id,
                "subagent_enabled": subagent_enabled,
            }
        )
        return "msg-stock-user", conversation_id or "conv-stock-1"

    async def process_agent_response(
        self,
        *,
        user_id: str,
        conversation_id: str,
        user_message_id: str,
        organization_id: str | None = None,
    ) -> None:
        self.process_calls.append(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
                "organization_id": organization_id,
            }
        )

    async def search_conversations(
        self,
        *,
        user_id: str,
        organization_id: str | None = None,
        status: ConversationStatus | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> SimpleNamespace:
        del user_id, organization_id, status, search, skip, limit
        return SimpleNamespace(items=[_conversation()], total=1)

    async def get_conversation_messages(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str | None = None,
    ) -> list[StockAgentMessage]:
        del conversation_id, user_id, organization_id
        return [
            _message(message_id="msg-stock-user"),
            _message(
                message_id="msg-stock-assistant",
                role=MessageRole.ASSISTANT,
                content="Stock analysis complete",
            ),
        ]

    async def get_conversation_plan(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str | None = None,
    ) -> dict[str, object]:
        del user_id, organization_id
        return {
            "conversation_id": conversation_id,
            "todos": [{"content": "Review price trend", "status": "completed"}],
            "summary": {
                "total": 1,
                "completed": 1,
                "in_progress": 0,
                "pending": 0,
            },
        }


def _build_test_app(
    skill_service: StockAgentSkillService,
    agent_service: _FakeStockAgentService | None = None,
) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(_request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.include_router(stock_agent_router)
    app.dependency_overrides[get_current_active_user] = _user
    app.dependency_overrides[get_current_organization_context] = (
        lambda: OrganizationContext(organization_id="org-1")
    )
    app.dependency_overrides[get_stock_agent_skill_service] = lambda: skill_service
    if agent_service is not None:
        app.dependency_overrides[get_stock_agent_service] = lambda: agent_service
    return app


@pytest.mark.asyncio
async def test_stock_agent_skill_endpoints_support_crud_and_enablement_flow() -> None:
    service = StockAgentSkillService(
        skill_repository=_InMemorySkillRepo(),
        access_repository=_InMemoryAccessRepo(),
        tool_catalog_provider=lambda: [
            StockAgentSelectableToolDescriptor(
                tool_name="customer_lookup",
                display_name="Customer Lookup",
                description="Look up customer records",
                category="crm",
            ),
            StockAgentSelectableToolDescriptor(
                tool_name="workspace_summary",
                display_name="Workspace Summary",
                description="Summarize workspace context",
                category="workspace",
            ),
        ],
    )
    app = _build_test_app(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        tools_response = await client.get("/stock-agent/tools")
        create_response = await client.post(
            "/stock-agent/skills",
            json={
                "name": "Revenue Research",
                "description": "Research and aggregate revenue context",
                "activation_prompt": "Use customer_lookup and workspace_summary",
                "allowed_tool_names": ["customer_lookup", "workspace_summary"],
            },
        )
        list_response = await client.get("/stock-agent/skills")
        enable_response = await client.put("/stock-agent/skills/revenue-research/enabled")
        detail_response = await client.get("/stock-agent/skills/revenue-research")
        update_response = await client.patch(
            "/stock-agent/skills/revenue-research",
            json={
                "name": "Revenue Research v2",
                "allowed_tool_names": ["customer_lookup"],
            },
        )
        disable_response = await client.delete(
            "/stock-agent/skills/revenue-research/enabled"
        )
        delete_response = await client.delete("/stock-agent/skills/revenue-research")

    assert tools_response.status_code == 200
    assert [item["tool_name"] for item in tools_response.json()["items"]] == [
        "customer_lookup",
        "workspace_summary",
    ]

    assert create_response.status_code == 201
    assert create_response.json()["skill_id"] == "revenue-research"
    assert create_response.json()["is_enabled"] is False

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["skill_id"] == "revenue-research"
    assert list_response.json()["items"][0]["is_enabled"] is False

    assert enable_response.status_code == 200
    assert enable_response.json() == {
        "skill_id": "revenue-research",
        "is_enabled": True,
    }

    assert detail_response.status_code == 200
    assert detail_response.json()["is_enabled"] is True

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Revenue Research v2"
    assert update_response.json()["skill_id"] == "revenue-research"
    assert update_response.json()["version"] == "1.0.1"

    assert disable_response.status_code == 200
    assert disable_response.json() == {
        "skill_id": "revenue-research",
        "is_enabled": False,
    }

    assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_stock_agent_skill_list_supports_search_and_filter_query_params() -> None:
    service = StockAgentSkillService(
        skill_repository=_InMemorySkillRepo(),
        access_repository=_InMemoryAccessRepo(),
        tool_catalog_provider=lambda: [
            StockAgentSelectableToolDescriptor(
                tool_name="customer_lookup",
                display_name="Customer Lookup",
                description="Look up customer records",
                category="crm",
            ),
        ],
    )
    app = _build_test_app(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        await client.post(
            "/stock-agent/skills",
            json={
                "name": "Alpha Research",
                "description": "Search alpha accounts",
                "activation_prompt": "Use customer_lookup",
                "allowed_tool_names": ["customer_lookup"],
            },
        )
        await client.post(
            "/stock-agent/skills",
            json={
                "name": "Beta Planner",
                "description": "Plan beta accounts",
                "activation_prompt": "Use customer_lookup",
                "allowed_tool_names": ["customer_lookup"],
            },
        )
        await client.put("/stock-agent/skills/alpha-research/enabled")

        search_response = await client.get("/stock-agent/skills", params={"search": "alpha"})
        enabled_response = await client.get(
            "/stock-agent/skills",
            params={"filter": "enabled"},
        )
        disabled_response = await client.get(
            "/stock-agent/skills",
            params={"filter": "disabled"},
        )

    assert search_response.status_code == 200
    assert search_response.json()["total"] == 1
    assert [item["skill_id"] for item in search_response.json()["items"]] == [
        "alpha-research"
    ]

    assert enabled_response.status_code == 200
    assert enabled_response.json()["total"] == 1
    assert [item["skill_id"] for item in enabled_response.json()["items"]] == [
        "alpha-research"
    ]
    assert enabled_response.json()["items"][0]["is_enabled"] is True

    assert disabled_response.status_code == 200
    assert disabled_response.json()["total"] == 1
    assert [item["skill_id"] for item in disabled_response.json()["items"]] == [
        "beta-planner"
    ]
    assert disabled_response.json()["items"][0]["is_enabled"] is False


@pytest.mark.asyncio
async def test_stock_agent_message_and_conversation_endpoints_use_stock_service() -> None:
    skill_service = StockAgentSkillService(
        skill_repository=_InMemorySkillRepo(),
        access_repository=_InMemoryAccessRepo(),
        tool_catalog_provider=lambda: [],
    )
    agent_service = _FakeStockAgentService()
    app = _build_test_app(skill_service, agent_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        catalog_response = await client.get("/stock-agent/catalog")
        send_response = await client.post(
            "/stock-agent/messages",
            json={
                "content": " Analyze VNM ",
                "provider": "openai",
                "model": "gpt-5.4",
                "reasoning": "medium",
                "subagent_enabled": True,
            },
        )
        conversations_response = await client.get("/stock-agent/conversations")
        messages_response = await client.get(
            "/stock-agent/conversations/conv-stock-1/messages"
        )
        plan_response = await client.get("/stock-agent/conversations/conv-stock-1/plan")
        rejected_response = await client.post(
            "/stock-agent/messages",
            json={
                "conversation_id": "lead-conversation-id",
                "content": "Should reject",
                "provider": "openai",
                "model": "gpt-5.4",
            },
        )

    assert catalog_response.status_code == 200
    assert catalog_response.json()["default_provider"] == "openai"
    assert catalog_response.json()["providers"]

    assert send_response.status_code == 200
    assert send_response.json() == {
        "user_message_id": "msg-stock-user",
        "conversation_id": "conv-stock-1",
    }
    assert agent_service.runtime_config_calls[0] == {
        "provider": "openai",
        "model": "gpt-5.4",
        "reasoning": "medium",
    }
    assert agent_service.send_message_calls == [
            {
                "user_id": "user-1",
                "content": "Analyze VNM",
                "conversation_id": None,
                "organization_id": "org-1",
                "subagent_enabled": True,
        }
    ]
    assert agent_service.process_calls == [
        {
            "user_id": "user-1",
            "conversation_id": "conv-stock-1",
            "user_message_id": "msg-stock-user",
            "organization_id": "org-1",
        }
    ]

    assert conversations_response.status_code == 200
    assert conversations_response.json()["total"] == 1
    assert conversations_response.json()["items"][0]["id"] == "conv-stock-1"

    assert messages_response.status_code == 200
    assert messages_response.json()["conversation_id"] == "conv-stock-1"
    assert [message["id"] for message in messages_response.json()["messages"]] == [
        "msg-stock-user",
        "msg-stock-assistant",
    ]

    assert plan_response.status_code == 200
    assert plan_response.json() == {
        "conversation_id": "conv-stock-1",
        "todos": [{"content": "Review price trend", "status": "completed"}],
        "summary": {
            "total": 1,
            "completed": 1,
            "in_progress": 0,
            "pending": 0,
        },
    }

    assert rejected_response.status_code == 404
    assert rejected_response.json() == {"detail": "Stock-agent conversation not found"}
