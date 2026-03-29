"""Resolve lead-agent skill access for the current caller scope."""

import logging
from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.domain.models.lead_agent_skill import LeadAgentSkill
from app.repo.lead_agent_skill_repo import LeadAgentSkillRepository
from app.repo.lead_agent_skill_access_repo import LeadAgentSkillAccessRepository

logger = logging.getLogger(__name__)


class ResolvedLeadAgentSkillAccess(BaseModel):
    """Enabled skill IDs for one runtime execution."""

    enabled_skill_ids: list[str] = Field(default_factory=list)


class LeadAgentSkillAccessResolver:
    """Resolve the current caller's enabled lead-agent skills."""

    def __init__(
        self,
        repository: LeadAgentSkillAccessRepository,
        skill_repository: LeadAgentSkillRepository,
    ) -> None:
        """Initialize the resolver with persistence helpers."""
        self.repository = repository
        self.skill_repository = skill_repository

    async def resolve_for_caller(
        self,
        user_id: str,
        organization_id: str,
    ) -> ResolvedLeadAgentSkillAccess:
        """Resolve the enabled skills for the current caller scope."""
        organization_record = await self.repository.get_by_scope(
            user_id=user_id,
            organization_id=organization_id,
        )
        if organization_record is not None:
            return ResolvedLeadAgentSkillAccess(
                enabled_skill_ids=await self._filter_known_skill_ids(
                    organization_record.enabled_skill_ids,
                    user_id=user_id,
                    organization_id=organization_id,
                )
            )

        return ResolvedLeadAgentSkillAccess(
            enabled_skill_ids=[],
        )

    async def resolve_enabled_skill_for_caller(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> LeadAgentSkill | None:
        """Resolve one enabled skill definition for the current caller scope."""
        normalized_skill_id = skill_id.strip()
        if not normalized_skill_id:
            return None

        return await self.skill_repository.get_accessible_by_skill_id(
            normalized_skill_id,
            user_id=user_id,
            organization_id=organization_id,
        )

    async def resolve_skill_definitions(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_ids: Sequence[str],
    ) -> list[LeadAgentSkill]:
        """Resolve ordered skill definitions for one caller-scoped skill list."""
        normalized_skill_ids = self._normalize_skill_ids(skill_ids)
        if not normalized_skill_ids:
            return []

        skills = await self.skill_repository.list_accessible(
            user_id=user_id,
            organization_id=organization_id,
            skill_ids=normalized_skill_ids,
        )
        skills_by_id = {skill.skill_id: skill for skill in skills}
        ordered_skills: list[LeadAgentSkill] = []

        for skill_id in normalized_skill_ids:
            skill = skills_by_id.get(skill_id)
            if skill is None:
                logger.warning(
                    "Ignoring unknown lead-agent skill id during definition resolution: %s",
                    skill_id,
                )
                continue
            ordered_skills.append(skill)

        return ordered_skills

    async def _filter_known_skill_ids(
        self,
        skill_ids: Sequence[str],
        *,
        user_id: str,
        organization_id: str,
    ) -> list[str]:
        """Keep only known skills while preserving caller-configured ordering."""
        known_skills = await self.skill_repository.list_accessible(
            user_id=user_id,
            organization_id=organization_id,
            skill_ids=skill_ids,
        )
        known_skill_ids = {skill.skill_id for skill in known_skills}
        filtered_skill_ids: list[str] = []
        seen: set[str] = set()

        for normalized_skill_id in self._normalize_skill_ids(skill_ids):
            if not normalized_skill_id or normalized_skill_id in seen:
                continue
            if normalized_skill_id not in known_skill_ids:
                logger.warning(
                    "Ignoring unknown lead-agent skill id in access configuration: %s",
                    normalized_skill_id,
                )
                continue
            seen.add(normalized_skill_id)
            filtered_skill_ids.append(normalized_skill_id)

        return filtered_skill_ids

    @staticmethod
    def _normalize_skill_ids(skill_ids: Sequence[str]) -> list[str]:
        """Normalize ordered skill IDs while removing blanks and duplicates."""
        normalized_skill_ids: list[str] = []
        seen: set[str] = set()

        for skill_id in skill_ids:
            normalized_skill_id = skill_id.strip()
            if not normalized_skill_id or normalized_skill_id in seen:
                continue
            seen.add(normalized_skill_id)
            normalized_skill_ids.append(normalized_skill_id)

        return normalized_skill_ids
