"""Repository for persisted user-created lead-agent skills."""

from collections.abc import Sequence
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
        skip: int = 0,
        limit: int = 20,
    ) -> LeadAgentSkillListResult:
        """List skills created by one user within the selected scope."""
        query: dict[str, Any] = {
            "created_by": user_id,
            "organization_id": organization_id,
        }

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("updated_at", -1).skip(skip).limit(
            limit
        )

        items: list[LeadAgentSkill] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(LeadAgentSkill(**doc))

        return LeadAgentSkillListResult(items=items, total=total)

    @staticmethod
    def _access_query(
        *,
        user_id: str,
        organization_id: str,
        skill_ids: Sequence[str] | None,
    ) -> dict[str, Any]:
        """Build a query for skills visible to the current caller."""
        query: dict[str, Any] = {
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
