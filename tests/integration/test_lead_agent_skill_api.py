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

from app.agents.implementations.lead_agent.tool_catalog import (
    LeadAgentSelectableToolDescriptor,
)
from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.ai.lead_agent import router as lead_agent_router
from app.common.exceptions import AppException
from app.common.service import get_lead_agent_skill_service
from app.domain.models.lead_agent_skill import LeadAgentSkill
from app.domain.models.lead_agent_skill_access import LeadAgentSkillAccess
from app.domain.models.user import User, UserRole
from app.repo.lead_agent_skill_repo import LeadAgentSkillListResult
from app.services.ai.lead_agent_skill_service import LeadAgentSkillService


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
        self.skills: dict[tuple[str, str, str], LeadAgentSkill] = {}
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
    ) -> LeadAgentSkillListResult:
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
        return LeadAgentSkillListResult(items=items[skip : skip + limit], total=len(items))

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
    ) -> LeadAgentSkill:
        self._counter += 1
        now = _now()
        skill = LeadAgentSkill(
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
    ) -> LeadAgentSkill | None:
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
    ) -> LeadAgentSkill | None:
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
        self.records: dict[tuple[str, str], LeadAgentSkillAccess] = {}
        self._counter = 0

    async def get_by_scope(
        self,
        user_id: str,
        organization_id: str,
    ) -> LeadAgentSkillAccess | None:
        return self.records.get((user_id, organization_id))

    async def upsert_enabled_skills(
        self,
        user_id: str,
        enabled_skill_ids: list[str],
        organization_id: str,
    ) -> LeadAgentSkillAccess:
        self._counter += 1
        now = _now()
        existing = self.records.get((user_id, organization_id))
        record = LeadAgentSkillAccess(
            _id=existing.id if existing is not None else f"access-{self._counter}",
            user_id=user_id,
            organization_id=organization_id,
            enabled_skill_ids=list(enabled_skill_ids),
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        self.records[(user_id, organization_id)] = record
        return record


def _build_test_app(skill_service: LeadAgentSkillService) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(_request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.include_router(lead_agent_router)
    app.dependency_overrides[get_current_active_user] = _user
    app.dependency_overrides[get_current_organization_context] = (
        lambda: OrganizationContext(organization_id="org-1")
    )
    app.dependency_overrides[get_lead_agent_skill_service] = lambda: skill_service
    return app


@pytest.mark.asyncio
async def test_lead_agent_skill_endpoints_support_crud_and_enablement_flow() -> None:
    service = LeadAgentSkillService(
        skill_repository=_InMemorySkillRepo(),
        access_repository=_InMemoryAccessRepo(),
        tool_catalog_provider=lambda: [
            LeadAgentSelectableToolDescriptor(
                tool_name="customer_lookup",
                display_name="Customer Lookup",
                description="Look up customer records",
                category="crm",
            ),
            LeadAgentSelectableToolDescriptor(
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
        tools_response = await client.get("/lead-agent/tools")
        create_response = await client.post(
            "/lead-agent/skills",
            json={
                "name": "Revenue Research",
                "description": "Research and aggregate revenue context",
                "activation_prompt": "Use customer_lookup and workspace_summary",
                "allowed_tool_names": ["customer_lookup", "workspace_summary"],
            },
        )
        list_response = await client.get("/lead-agent/skills")
        enable_response = await client.put("/lead-agent/skills/revenue-research/enabled")
        detail_response = await client.get("/lead-agent/skills/revenue-research")
        update_response = await client.patch(
            "/lead-agent/skills/revenue-research",
            json={
                "name": "Revenue Research v2",
                "allowed_tool_names": ["customer_lookup"],
            },
        )
        disable_response = await client.delete(
            "/lead-agent/skills/revenue-research/enabled"
        )
        delete_response = await client.delete("/lead-agent/skills/revenue-research")

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
async def test_lead_agent_skill_list_supports_search_and_filter_query_params() -> None:
    service = LeadAgentSkillService(
        skill_repository=_InMemorySkillRepo(),
        access_repository=_InMemoryAccessRepo(),
        tool_catalog_provider=lambda: [
            LeadAgentSelectableToolDescriptor(
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
            "/lead-agent/skills",
            json={
                "name": "Alpha Research",
                "description": "Search alpha accounts",
                "activation_prompt": "Use customer_lookup",
                "allowed_tool_names": ["customer_lookup"],
            },
        )
        await client.post(
            "/lead-agent/skills",
            json={
                "name": "Beta Planner",
                "description": "Plan beta accounts",
                "activation_prompt": "Use customer_lookup",
                "allowed_tool_names": ["customer_lookup"],
            },
        )
        await client.put("/lead-agent/skills/alpha-research/enabled")

        search_response = await client.get("/lead-agent/skills", params={"search": "alpha"})
        enabled_response = await client.get(
            "/lead-agent/skills",
            params={"filter": "enabled"},
        )
        disabled_response = await client.get(
            "/lead-agent/skills",
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
