"""Service layer for user-managed lead-agent skills."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence

from app.agents.implementations.lead_agent.tool_catalog import (
    LeadAgentSelectableToolDescriptor,
    get_lead_agent_selectable_tool_catalog,
)
from app.common.exceptions.ai_exceptions import (
    InvalidLeadAgentSkillConfigurationError,
    LeadAgentSkillNotFoundError,
)
from app.domain.models.lead_agent_skill import LeadAgentSkill
from app.domain.schemas.lead_agent import (
    LeadAgentCreateSkillRequest,
    LeadAgentSkillFilterStatus,
    LeadAgentSkillEnablementResponse,
    LeadAgentSkillListResponse,
    LeadAgentSkillResponse,
    LeadAgentToolListResponse,
    LeadAgentToolResponse,
    LeadAgentUpdateSkillRequest,
)
from app.repo.lead_agent_skill_access_repo import LeadAgentSkillAccessRepository
from app.repo.lead_agent_skill_repo import LeadAgentSkillRepository


class LeadAgentSkillService:
    """Manage user-scoped lead-agent skill CRUD and enablement."""

    def __init__(
        self,
        skill_repository: LeadAgentSkillRepository,
        access_repository: LeadAgentSkillAccessRepository,
        tool_catalog_provider: Callable[
            [], Sequence[LeadAgentSelectableToolDescriptor]
        ] = get_lead_agent_selectable_tool_catalog,
    ) -> None:
        self.skill_repository = skill_repository
        self.access_repository = access_repository
        self.tool_catalog_provider = tool_catalog_provider

    async def list_tools(self) -> LeadAgentToolListResponse:
        """Return the current user-selectable lead-agent tool catalog."""
        return LeadAgentToolListResponse(
            items=[
                LeadAgentToolResponse(
                    tool_name=tool.tool_name,
                    display_name=tool.display_name,
                    description=tool.description,
                    category=tool.category,
                )
                for tool in self.tool_catalog_provider()
            ]
        )

    async def list_skills(
        self,
        *,
        user_id: str,
        organization_id: str,
        search: str | None = None,
        skill_filter: LeadAgentSkillFilterStatus = LeadAgentSkillFilterStatus.ALL,
        skip: int = 0,
        limit: int = 20,
    ) -> LeadAgentSkillListResponse:
        """List the caller's skills within the current organization."""
        enabled_skill_ids = await self._get_enabled_skill_ids(
            user_id=user_id,
            organization_id=organization_id,
        )
        include_skill_ids: list[str] | None = None
        exclude_skill_ids: list[str] | None = None
        if skill_filter == LeadAgentSkillFilterStatus.ENABLED:
            if not enabled_skill_ids:
                return LeadAgentSkillListResponse(
                    items=[],
                    total=0,
                    skip=skip,
                    limit=limit,
                )
            include_skill_ids = enabled_skill_ids
        elif skill_filter == LeadAgentSkillFilterStatus.DISABLED:
            exclude_skill_ids = enabled_skill_ids

        result = await self.skill_repository.list_by_creator(
            user_id=user_id,
            organization_id=organization_id,
            search=search,
            include_skill_ids=include_skill_ids,
            exclude_skill_ids=exclude_skill_ids,
            skip=skip,
            limit=limit,
        )
        enabled_skill_ids_set = set(enabled_skill_ids)
        return LeadAgentSkillListResponse(
            items=[
                self._to_skill_response(
                    skill,
                    is_enabled=skill.skill_id in enabled_skill_ids_set,
                )
                for skill in result.items
            ],
            total=result.total,
            skip=skip,
            limit=limit,
        )

    async def create_skill(
        self,
        *,
        user_id: str,
        organization_id: str,
        request: LeadAgentCreateSkillRequest,
    ) -> LeadAgentSkillResponse:
        """Create one new caller-owned skill."""
        allowed_tool_names = self._validate_allowed_tool_names(request.allowed_tool_names)
        skill_id = await self._generate_skill_id(
            user_id=user_id,
            organization_id=organization_id,
            name=request.name,
        )
        skill = await self.skill_repository.create(
            skill_id=skill_id,
            name=request.name,
            description=request.description,
            activation_prompt=request.activation_prompt,
            allowed_tool_names=allowed_tool_names,
            version="1.0.0",
            created_by=user_id,
            organization_id=organization_id,
        )
        return self._to_skill_response(skill, is_enabled=False)

    async def get_skill(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> LeadAgentSkillResponse:
        """Return one caller-owned skill."""
        skill = await self._require_owned_skill(
            user_id=user_id,
            organization_id=organization_id,
            skill_id=skill_id,
        )
        enabled_skill_ids = set(
            await self._get_enabled_skill_ids(
                user_id=user_id,
                organization_id=organization_id,
            )
        )
        return self._to_skill_response(
            skill,
            is_enabled=skill.skill_id in enabled_skill_ids,
        )

    async def update_skill(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
        request: LeadAgentUpdateSkillRequest,
    ) -> LeadAgentSkillResponse:
        """Update one caller-owned skill and bump its patch version."""
        if not any(
            value is not None
            for value in (
                request.name,
                request.description,
                request.activation_prompt,
                request.allowed_tool_names,
            )
        ):
            raise InvalidLeadAgentSkillConfigurationError(
                "At least one skill field must be provided for update"
            )

        current_skill = await self._require_owned_skill(
            user_id=user_id,
            organization_id=organization_id,
            skill_id=skill_id,
        )
        allowed_tool_names = (
            self._validate_allowed_tool_names(request.allowed_tool_names)
            if request.allowed_tool_names is not None
            else None
        )
        updated_skill = await self.skill_repository.update_by_creator_and_skill_id(
            user_id=user_id,
            organization_id=organization_id,
            skill_id=current_skill.skill_id,
            name=request.name,
            description=request.description,
            activation_prompt=request.activation_prompt,
            allowed_tool_names=allowed_tool_names,
            version=self._bump_patch_version(current_skill.version),
        )
        if updated_skill is None:
            raise LeadAgentSkillNotFoundError()

        enabled_skill_ids = set(
            await self._get_enabled_skill_ids(
                user_id=user_id,
                organization_id=organization_id,
            )
        )
        return self._to_skill_response(
            updated_skill,
            is_enabled=updated_skill.skill_id in enabled_skill_ids,
        )

    async def delete_skill(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> None:
        """Delete one caller-owned skill and prune its enabled state."""
        skill = await self._require_owned_skill(
            user_id=user_id,
            organization_id=organization_id,
            skill_id=skill_id,
        )
        deleted = await self.skill_repository.delete_by_creator_and_skill_id(
            user_id=user_id,
            organization_id=organization_id,
            skill_id=skill.skill_id,
        )
        if not deleted:
            raise LeadAgentSkillNotFoundError()

        record = await self.access_repository.get_by_scope(
            user_id=user_id,
            organization_id=organization_id,
        )
        if record is None:
            return

        enabled_skill_ids = [
            enabled_skill_id
            for enabled_skill_id in self._normalize_strings(record.enabled_skill_ids)
            if enabled_skill_id != skill.skill_id
        ]
        await self.access_repository.upsert_enabled_skills(
            user_id=user_id,
            organization_id=organization_id,
            enabled_skill_ids=enabled_skill_ids,
        )

    async def enable_skill(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> LeadAgentSkillEnablementResponse:
        """Enable one caller-owned skill."""
        skill = await self._require_owned_skill(
            user_id=user_id,
            organization_id=organization_id,
            skill_id=skill_id,
        )
        enabled_skill_ids = await self._get_enabled_skill_ids(
            user_id=user_id,
            organization_id=organization_id,
        )
        if skill.skill_id not in enabled_skill_ids:
            enabled_skill_ids.append(skill.skill_id)
            await self.access_repository.upsert_enabled_skills(
                user_id=user_id,
                organization_id=organization_id,
                enabled_skill_ids=enabled_skill_ids,
            )

        return LeadAgentSkillEnablementResponse(
            skill_id=skill.skill_id,
            is_enabled=True,
        )

    async def disable_skill(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> LeadAgentSkillEnablementResponse:
        """Disable one caller-owned skill."""
        skill = await self._require_owned_skill(
            user_id=user_id,
            organization_id=organization_id,
            skill_id=skill_id,
        )
        record = await self.access_repository.get_by_scope(
            user_id=user_id,
            organization_id=organization_id,
        )
        if record is not None:
            enabled_skill_ids = [
                enabled_skill_id
                for enabled_skill_id in self._normalize_strings(record.enabled_skill_ids)
                if enabled_skill_id != skill.skill_id
            ]
            await self.access_repository.upsert_enabled_skills(
                user_id=user_id,
                organization_id=organization_id,
                enabled_skill_ids=enabled_skill_ids,
            )

        return LeadAgentSkillEnablementResponse(
            skill_id=skill.skill_id,
            is_enabled=False,
        )

    async def _require_owned_skill(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> LeadAgentSkill:
        """Return one owned skill or raise a not-found error."""
        normalized_skill_id = skill_id.strip()
        if not normalized_skill_id:
            raise LeadAgentSkillNotFoundError()

        skill = await self.skill_repository.get_by_creator_and_skill_id(
            user_id=user_id,
            organization_id=organization_id,
            skill_id=normalized_skill_id,
        )
        if skill is None:
            raise LeadAgentSkillNotFoundError()
        return skill

    async def _get_enabled_skill_ids(
        self,
        *,
        user_id: str,
        organization_id: str,
    ) -> list[str]:
        """Return the caller's enabled skill IDs for one organization."""
        record = await self.access_repository.get_by_scope(
            user_id=user_id,
            organization_id=organization_id,
        )
        if record is None:
            return []
        return self._normalize_strings(record.enabled_skill_ids)

    async def _generate_skill_id(
        self,
        *,
        user_id: str,
        organization_id: str,
        name: str,
    ) -> str:
        """Generate a unique caller-scoped skill ID from the display name."""
        base_skill_id = self._slugify(name)
        candidate_skill_id = base_skill_id
        suffix = 2

        while await self.skill_repository.exists_by_creator_and_skill_id(
            user_id=user_id,
            organization_id=organization_id,
            skill_id=candidate_skill_id,
        ):
            candidate_skill_id = f"{base_skill_id}-{suffix}"
            suffix += 1

        return candidate_skill_id

    def _validate_allowed_tool_names(self, tool_names: Sequence[str]) -> list[str]:
        """Validate requested tool names against the selectable catalog."""
        normalized_tool_names = self._normalize_strings(tool_names)
        allowed_tool_names = {
            tool.tool_name for tool in self.tool_catalog_provider()
        }
        invalid_tool_names = [
            tool_name
            for tool_name in normalized_tool_names
            if tool_name not in allowed_tool_names
        ]
        if invalid_tool_names:
            raise InvalidLeadAgentSkillConfigurationError(
                "Unknown or unavailable lead-agent tools: "
                + ", ".join(invalid_tool_names)
            )
        return normalized_tool_names

    @staticmethod
    def _to_skill_response(
        skill: LeadAgentSkill,
        *,
        is_enabled: bool,
    ) -> LeadAgentSkillResponse:
        """Convert one persisted skill model into an API response."""
        return LeadAgentSkillResponse(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            activation_prompt=skill.activation_prompt,
            allowed_tool_names=skill.allowed_tool_names,
            version=skill.version,
            is_enabled=is_enabled,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        )

    @staticmethod
    def _normalize_strings(values: Sequence[str] | None) -> list[str]:
        """Normalize, deduplicate, and preserve the order of one string list."""
        if values is None:
            return []

        normalized_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized_value = str(value).strip()
            if not normalized_value or normalized_value in seen:
                continue
            seen.add(normalized_value)
            normalized_values.append(normalized_value)
        return normalized_values

    @staticmethod
    def _slugify(value: str) -> str:
        """Convert a display name into a stable, URL-safe skill ID stem."""
        normalized_value = unicodedata.normalize("NFKD", value)
        ascii_value = normalized_value.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
        return slug or "skill"

    @staticmethod
    def _bump_patch_version(version: str) -> str:
        """Increment the patch segment of a semantic version string."""
        parts = version.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            return "1.0.1"

        major, minor, patch = (int(part) for part in parts)
        return f"{major}.{minor}.{patch + 1}"
