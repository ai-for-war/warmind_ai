"""Repository helpers for organization-scoped lead-agent skill access persistence."""

from collections.abc import Sequence
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.models.lead_agent_skill_access import LeadAgentSkillAccess


class LeadAgentSkillAccessRepository:
    """Persist per-user, per-organization lead-agent skill access records."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize the repository with the shared Mongo database."""
        self.collection = db.lead_agent_skill_access

    async def get_by_scope(
        self,
        user_id: str,
        organization_id: str,
    ) -> LeadAgentSkillAccess | None:
        """Return the access record for one caller scope."""
        doc = await self.collection.find_one(
            {
                "user_id": user_id,
                "organization_id": organization_id,
            }
        )
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return LeadAgentSkillAccess(**doc)

    async def list_by_user(self, user_id: str) -> list[LeadAgentSkillAccess]:
        """List all access records for a user across organization scopes."""
        cursor = self.collection.find({"user_id": user_id}).sort(
            [("organization_id", 1), ("updated_at", -1)]
        )

        records: list[LeadAgentSkillAccess] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            records.append(LeadAgentSkillAccess(**doc))
        return records

    async def upsert_enabled_skills(
        self,
        user_id: str,
        enabled_skill_ids: Sequence[str],
        organization_id: str,
    ) -> LeadAgentSkillAccess:
        """Create or replace the enabled skill set for one caller scope."""
        now = datetime.now(timezone.utc)
        normalized_skill_ids = self._normalize_skill_ids(enabled_skill_ids)

        doc = await self.collection.find_one_and_update(
            {
                "user_id": user_id,
                "organization_id": organization_id,
            },
            {
                "$set": {
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "enabled_skill_ids": normalized_skill_ids,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=True,
        )

        doc["_id"] = str(doc["_id"])
        return LeadAgentSkillAccess(**doc)

    async def delete_by_scope(
        self,
        user_id: str,
        organization_id: str,
    ) -> int:
        """Delete the access record for one caller scope."""
        result = await self.collection.delete_many(
            {
                "user_id": user_id,
                "organization_id": organization_id,
            }
        )
        return result.deleted_count

    @staticmethod
    def _normalize_skill_ids(skill_ids: Sequence[str]) -> list[str]:
        """Normalize, deduplicate, and preserve skill ID ordering."""
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for skill_id in skill_ids:
            normalized_skill_id = skill_id.strip()
            if not normalized_skill_id or normalized_skill_id in seen:
                continue
            seen.add(normalized_skill_id)
            normalized_ids.append(normalized_skill_id)
        return normalized_ids
