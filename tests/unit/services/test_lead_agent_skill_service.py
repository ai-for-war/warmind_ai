from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agents.implementations.lead_agent.tool_catalog import (
    LeadAgentSelectableToolDescriptor,
)
from app.common.exceptions.ai_exceptions import (
    InvalidLeadAgentSkillConfigurationError,
)
from app.domain.models.lead_agent_skill import LeadAgentSkill
from app.domain.models.lead_agent_skill_access import LeadAgentSkillAccess
from app.domain.schemas.lead_agent import (
    LeadAgentCreateSkillRequest,
    LeadAgentUpdateSkillRequest,
)
from app.repo.lead_agent_skill_repo import LeadAgentSkillListResult
from app.services.ai.lead_agent_skill_service import LeadAgentSkillService


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
        skip: int = 0,
        limit: int = 20,
    ) -> LeadAgentSkillListResult:
        items = [
            skill
            for (created_by, org_id, _skill_id), skill in self.skills.items()
            if created_by == user_id and org_id == organization_id
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


def _service(
    *,
    skill_repo: _InMemorySkillRepo | None = None,
    access_repo: _InMemoryAccessRepo | None = None,
) -> LeadAgentSkillService:
    return LeadAgentSkillService(
        skill_repository=skill_repo or _InMemorySkillRepo(),
        access_repository=access_repo or _InMemoryAccessRepo(),
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


@pytest.mark.asyncio
async def test_create_skill_slugifies_name_and_normalizes_tool_names() -> None:
    service = _service()

    created = await service.create_skill(
        user_id="user-1",
        organization_id="org-1",
        request=LeadAgentCreateSkillRequest(
            name=" Sales Research ",
            description="Find useful context",
            activation_prompt="Use customer_lookup carefully",
            allowed_tool_names=[
                "customer_lookup",
                " workspace_summary ",
                "customer_lookup",
            ],
        ),
    )

    assert created.skill_id == "sales-research"
    assert created.allowed_tool_names == ["customer_lookup", "workspace_summary"]
    assert created.version == "1.0.0"
    assert created.is_enabled is False


@pytest.mark.asyncio
async def test_create_skill_appends_suffix_only_within_same_user_scope() -> None:
    service = _service()

    first = await service.create_skill(
        user_id="user-1",
        organization_id="org-1",
        request=LeadAgentCreateSkillRequest(
            name="Sales Research",
            description="desc",
            activation_prompt="prompt",
            allowed_tool_names=["customer_lookup"],
        ),
    )
    second = await service.create_skill(
        user_id="user-1",
        organization_id="org-1",
        request=LeadAgentCreateSkillRequest(
            name="Sales Research",
            description="desc",
            activation_prompt="prompt",
            allowed_tool_names=["customer_lookup"],
        ),
    )
    other_user = await service.create_skill(
        user_id="user-2",
        organization_id="org-1",
        request=LeadAgentCreateSkillRequest(
            name="Sales Research",
            description="desc",
            activation_prompt="prompt",
            allowed_tool_names=["customer_lookup"],
        ),
    )

    assert first.skill_id == "sales-research"
    assert second.skill_id == "sales-research-2"
    assert other_user.skill_id == "sales-research"


@pytest.mark.asyncio
async def test_update_skill_bumps_patch_version_and_keeps_skill_id() -> None:
    service = _service()
    created = await service.create_skill(
        user_id="user-1",
        organization_id="org-1",
        request=LeadAgentCreateSkillRequest(
            name="Revenue QA",
            description="desc",
            activation_prompt="prompt",
            allowed_tool_names=["workspace_summary"],
        ),
    )

    updated = await service.update_skill(
        user_id="user-1",
        organization_id="org-1",
        skill_id=created.skill_id,
        request=LeadAgentUpdateSkillRequest(
            name="Revenue Quality Audit",
            allowed_tool_names=["customer_lookup"],
        ),
    )

    assert updated.skill_id == created.skill_id
    assert updated.name == "Revenue Quality Audit"
    assert updated.allowed_tool_names == ["customer_lookup"]
    assert updated.version == "1.0.1"


@pytest.mark.asyncio
async def test_enable_disable_and_delete_prune_access_state() -> None:
    skill_repo = _InMemorySkillRepo()
    access_repo = _InMemoryAccessRepo()
    service = _service(skill_repo=skill_repo, access_repo=access_repo)
    created = await service.create_skill(
        user_id="user-1",
        organization_id="org-1",
        request=LeadAgentCreateSkillRequest(
            name="Ops skill",
            description="desc",
            activation_prompt="prompt",
            allowed_tool_names=["customer_lookup"],
        ),
    )

    enabled = await service.enable_skill(
        user_id="user-1",
        organization_id="org-1",
        skill_id=created.skill_id,
    )
    listed = await service.list_skills(
        user_id="user-1",
        organization_id="org-1",
    )
    disabled = await service.disable_skill(
        user_id="user-1",
        organization_id="org-1",
        skill_id=created.skill_id,
    )
    await service.enable_skill(
        user_id="user-1",
        organization_id="org-1",
        skill_id=created.skill_id,
    )
    await service.delete_skill(
        user_id="user-1",
        organization_id="org-1",
        skill_id=created.skill_id,
    )

    assert enabled.is_enabled is True
    assert listed.items[0].is_enabled is True
    assert disabled.is_enabled is False
    assert access_repo.records[("user-1", "org-1")].enabled_skill_ids == []


@pytest.mark.asyncio
async def test_rejects_unknown_or_internal_tool_names() -> None:
    service = _service()

    with pytest.raises(InvalidLeadAgentSkillConfigurationError) as exc_info:
        await service.create_skill(
            user_id="user-1",
            organization_id="org-1",
            request=LeadAgentCreateSkillRequest(
                name="Unsafe skill",
                description="desc",
                activation_prompt="prompt",
                allowed_tool_names=["load_skill", "unknown"],
            ),
        )

    assert "Unknown or unavailable lead-agent tools" in exc_info.value.message


@pytest.mark.asyncio
async def test_update_requires_at_least_one_field() -> None:
    service = _service()
    created = await service.create_skill(
        user_id="user-1",
        organization_id="org-1",
        request=LeadAgentCreateSkillRequest(
            name="Planner",
            description="desc",
            activation_prompt="prompt",
            allowed_tool_names=[],
        ),
    )

    with pytest.raises(InvalidLeadAgentSkillConfigurationError):
        await service.update_skill(
            user_id="user-1",
            organization_id="org-1",
            skill_id=created.skill_id,
            request=LeadAgentUpdateSkillRequest(),
        )
