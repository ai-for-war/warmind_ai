"""Repository for persisted user-created lead-agent skills."""

from collections.abc import Sequence
from datetime import datetime, timezone
import re
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.domain.models.lead_agent_skill import LeadAgentSkill


class LeadAgentSkillListResult(BaseModel):
    """Paginated lead-agent skill query result."""

    items: list[LeadAgentSkill]
    total: int


class LeadAgentSkillRepository:
    """Persist and resolve user-created lead-agent skills."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize the repository with the shared Mongo database."""
        self.collection = db.lead_agent_skills

    async def get_accessible_by_skill_id(
        self,
        skill_id: str,
        *,
        user_id: str,
        organization_id: str,
    ) -> LeadAgentSkill | None:
        """Return one accessible skill definition for the current caller."""
        doc = await self.collection.find_one(
            self._access_query(
                user_id=user_id,
                organization_id=organization_id,
                skill_ids=[skill_id],
            )
        )
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return LeadAgentSkill(**doc)

    async def get_by_creator_and_skill_id(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> LeadAgentSkill | None:
        """Return one owned skill definition for the current caller."""
        doc = await self.collection.find_one(
            {
                "created_by": user_id,
                "organization_id": organization_id,
                "skill_id": skill_id,
            }
        )
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return LeadAgentSkill(**doc)

    async def list_accessible(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_ids: Sequence[str] | None = None,
    ) -> list[LeadAgentSkill]:
        """List accessible skill definitions for the current caller."""
        query = self._access_query(
            user_id=user_id,
            organization_id=organization_id,
            skill_ids=skill_ids,
        )
        cursor = self.collection.find(query).sort("updated_at", -1)

        skills: list[LeadAgentSkill] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            skills.append(LeadAgentSkill(**doc))
        return skills

    async def list_by_creator(
        self,
        *,
        user_id: str,
        organization_id: str,
        search: str | None = None,
        include_skill_ids: Sequence[str] | None = None,
        exclude_skill_ids: Sequence[str] | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> LeadAgentSkillListResult:
        """List skills created by one user within the selected scope."""
        query: dict[str, Any] = {
            "created_by": user_id,
            "organization_id": organization_id,
        }
        normalized_search = search.strip() if search is not None else ""
        if normalized_search:
            query["name"] = {
                "$regex": re.escape(normalized_search),
                "$options": "i",
            }

        normalized_include_skill_ids = self._normalize_skill_ids(include_skill_ids)
        if normalized_include_skill_ids:
            query["skill_id"] = {"$in": normalized_include_skill_ids}

        normalized_exclude_skill_ids = self._normalize_skill_ids(exclude_skill_ids)
        if normalized_exclude_skill_ids:
            query.setdefault("skill_id", {})
            query["skill_id"]["$nin"] = normalized_exclude_skill_ids

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("updated_at", -1).skip(skip).limit(
            limit
        )

        items: list[LeadAgentSkill] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(LeadAgentSkill(**doc))

        return LeadAgentSkillListResult(items=items, total=total)

    async def create(
        self,
        *,
        skill_id: str,
        name: str,
        description: str,
        activation_prompt: str,
        allowed_tool_names: Sequence[str],
        version: str,
        created_by: str,
        organization_id: str,
    ) -> LeadAgentSkill:
        """Create one owned skill definition."""
        now = datetime.now(timezone.utc)
        doc = {
            "skill_id": skill_id,
            "name": name,
            "description": description,
            "activation_prompt": activation_prompt,
            "allowed_tool_names": self._normalize_skill_ids(allowed_tool_names),
            "version": version,
            "created_by": created_by,
            "organization_id": organization_id,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return LeadAgentSkill(**doc)

    async def update_by_creator_and_skill_id(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        activation_prompt: str | None = None,
        allowed_tool_names: Sequence[str] | None = None,
        version: str | None = None,
    ) -> LeadAgentSkill | None:
        """Update one owned skill definition."""
        update_data: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if activation_prompt is not None:
            update_data["activation_prompt"] = activation_prompt
        if allowed_tool_names is not None:
            update_data["allowed_tool_names"] = self._normalize_skill_ids(
                allowed_tool_names
            )
        if version is not None:
            update_data["version"] = version

        doc = await self.collection.find_one_and_update(
            {
                "created_by": user_id,
                "organization_id": organization_id,
                "skill_id": skill_id,
            },
            {"$set": update_data},
            return_document=True,
        )
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return LeadAgentSkill(**doc)

    async def delete_by_creator_and_skill_id(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> bool:
        """Delete one owned skill definition."""
        result = await self.collection.delete_one(
            {
                "created_by": user_id,
                "organization_id": organization_id,
                "skill_id": skill_id,
            }
        )
        return result.deleted_count > 0

    async def exists_by_creator_and_skill_id(
        self,
        *,
        user_id: str,
        organization_id: str,
        skill_id: str,
    ) -> bool:
        """Return True when the caller already owns the given skill ID."""
        return (
            await self.collection.count_documents(
                {
                    "created_by": user_id,
                    "organization_id": organization_id,
                    "skill_id": skill_id,
                },
                limit=1,
            )
        ) > 0

    @staticmethod
    def _access_query(
        *,
        user_id: str,
        organization_id: str,
        skill_ids: Sequence[str] | None,
    ) -> dict[str, Any]:
        """Build a query for skills visible to the current caller."""
        query: dict[str, Any] = {
            "created_by": user_id,
            "organization_id": organization_id,
        }

        normalized_skill_ids = LeadAgentSkillRepository._normalize_skill_ids(skill_ids)
        if normalized_skill_ids:
            query["skill_id"] = {"$in": normalized_skill_ids}

        return query

    @staticmethod
    def _normalize_skill_ids(skill_ids: Sequence[str] | None) -> list[str]:
        """Normalize skill IDs used for query filtering."""
        if skill_ids is None:
            return []

        normalized_ids: list[str] = []
        seen: set[str] = set()
        for skill_id in skill_ids:
            normalized_skill_id = skill_id.strip()
            if not normalized_skill_id or normalized_skill_id in seen:
                continue
            seen.add(normalized_skill_id)
            normalized_ids.append(normalized_skill_id)
        return normalized_ids
