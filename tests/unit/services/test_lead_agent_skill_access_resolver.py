from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.models.lead_agent_skill import LeadAgentSkill
from app.domain.models.lead_agent_skill_access import LeadAgentSkillAccess
from app.services.ai.lead_agent_skill_access_resolver import LeadAgentSkillAccessResolver


def _record(
    *,
    user_id: str = "user-1",
    organization_id: str | None = "org-1",
    enabled_skill_ids: list[str] | None = None,
) -> LeadAgentSkillAccess:
    now = datetime.now(timezone.utc)
    return LeadAgentSkillAccess(
        _id="record-1",
        user_id=user_id,
        organization_id=organization_id,
        enabled_skill_ids=enabled_skill_ids or [],
        created_at=now,
        updated_at=now,
    )


def _repo() -> SimpleNamespace:
    return SimpleNamespace(get_by_scope=AsyncMock())


def _skill(skill_id: str) -> LeadAgentSkill:
    now = datetime.now(timezone.utc)
    return LeadAgentSkill(
        _id=f"{skill_id}-id",
        skill_id=skill_id,
        name=skill_id.title(),
        description=f"{skill_id} description",
        activation_prompt=f"{skill_id} activation",
        allowed_tool_names=[],
        version="1.0.0",
        created_by="user-1",
        organization_id="org-1",
        created_at=now,
        updated_at=now,
    )


def _registry(known_skill_ids: set[str]) -> SimpleNamespace:
    async def _list_accessible(
        *,
        user_id: str,
        organization_id: str,
        skill_ids: list[str] | None = None,
    ) -> list[LeadAgentSkill]:
        del user_id, organization_id
        ordered_ids = list(skill_ids or known_skill_ids)
        skills: list[LeadAgentSkill] = []
        seen: set[str] = set()
        for skill_id in ordered_ids:
            if skill_id in seen or skill_id not in known_skill_ids:
                continue
            seen.add(skill_id)
            skills.append(_skill(skill_id))
        return skills

    async def _get_accessible_by_skill_id(
        skill_id: str,
        *,
        user_id: str,
        organization_id: str,
    ) -> LeadAgentSkill | None:
        del user_id, organization_id
        normalized_skill_id = skill_id.strip()
        if normalized_skill_id not in known_skill_ids:
            return None
        return _skill(normalized_skill_id)

    return SimpleNamespace(
        list_accessible=AsyncMock(side_effect=_list_accessible),
        get_accessible_by_skill_id=AsyncMock(side_effect=_get_accessible_by_skill_id),
    )


@pytest.mark.asyncio
async def test_resolver_prefers_organization_record_and_filters_unknown_skills() -> None:
    repository = _repo()
    registry = _registry({"sales-playbook", "web-research"})
    repository.get_by_scope.return_value = _record(
        organization_id="org-1",
        enabled_skill_ids=[
            "sales-playbook",
            "unknown-skill",
            "sales-playbook",
            "web-research",
        ],
    )
    resolver = LeadAgentSkillAccessResolver(
        repository=repository,
        skill_repository=registry,
    )

    resolved = await resolver.resolve_for_caller(
        user_id="user-1",
        organization_id="org-1",
    )

    assert resolved.enabled_skill_ids == ["sales-playbook", "web-research"]
    repository.get_by_scope.assert_awaited_once_with(
        user_id="user-1",
        organization_id="org-1",
    )


@pytest.mark.asyncio
async def test_resolver_returns_no_access_when_org_record_is_missing() -> None:
    repository = _repo()
    registry = _registry(set())
    repository.get_by_scope.return_value = None
    resolver = LeadAgentSkillAccessResolver(
        repository=repository,
        skill_repository=registry,
    )

    resolved = await resolver.resolve_for_caller(
        user_id="user-1",
        organization_id="org-1",
    )

    assert resolved.enabled_skill_ids == []
    repository.get_by_scope.assert_awaited_once_with(
        user_id="user-1",
        organization_id="org-1",
    )


@pytest.mark.asyncio
async def test_resolver_returns_no_access_when_records_are_missing() -> None:
    repository = _repo()
    registry = _registry(set())
    repository.get_by_scope.return_value = None
    resolver = LeadAgentSkillAccessResolver(
        repository=repository,
        skill_repository=registry,
    )

    resolved = await resolver.resolve_for_caller(
        user_id="user-1",
        organization_id="org-1",
    )

    assert resolved.enabled_skill_ids == []


@pytest.mark.asyncio
async def test_resolver_returns_enabled_skill_definition_for_caller() -> None:
    repository = _repo()
    registry = _registry({"web-research"})
    repository.get_by_scope.return_value = _record(
        organization_id="org-1",
        enabled_skill_ids=["web-research"],
    )
    resolver = LeadAgentSkillAccessResolver(
        repository=repository,
        skill_repository=registry,
    )

    resolved_skill = await resolver.resolve_enabled_skill_for_caller(
        user_id="user-1",
        organization_id="org-1",
        skill_id=" web-research ",
    )

    assert resolved_skill is not None
    assert resolved_skill.skill_id == "web-research"
    registry.get_accessible_by_skill_id.assert_awaited_once_with(
        "web-research",
        user_id="user-1",
        organization_id="org-1",
    )


@pytest.mark.asyncio
async def test_resolver_rejects_disabled_skill_definition_lookup() -> None:
    repository = _repo()
    registry = _registry({"web-research"})
    repository.get_by_scope.return_value = _record(
        organization_id="org-1",
        enabled_skill_ids=["web-research"],
    )
    resolver = LeadAgentSkillAccessResolver(
        repository=repository,
        skill_repository=registry,
    )

    resolved_skill = await resolver.resolve_enabled_skill_for_caller(
        user_id="user-1",
        organization_id="org-1",
        skill_id="finance-ops",
    )

    assert resolved_skill is None
    registry.get_accessible_by_skill_id.assert_not_awaited()
    registry.list_accessible.assert_awaited_once()
