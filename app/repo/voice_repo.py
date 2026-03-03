"""Voice repository for database operations."""

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.domain.models.voice import Voice


class VoiceListResult(BaseModel):
    """Paginated voice query result."""

    items: list[Voice]
    total: int


class VoiceRepository:
    """Repository for voice metadata operations with soft delete support."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize VoiceRepository with database instance."""
        self.collection = db.voices

    async def create(self, voice_data: dict[str, Any]) -> Voice:
        """Insert voice metadata into voices collection."""
        data = dict(voice_data)
        data.setdefault("created_at", datetime.now(timezone.utc))
        data.setdefault("deleted_at", None)

        result = await self.collection.insert_one(data)
        data["_id"] = str(result.inserted_id)
        return Voice(**data)

    async def find_by_id(self, voice_db_id: str) -> Optional[Voice]:
        """Find non-deleted voice by MongoDB _id."""
        try:
            object_id = ObjectId(voice_db_id)
        except (TypeError, ValueError, InvalidId):
            return None

        doc = await self.collection.find_one({"_id": object_id, "deleted_at": None})
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return Voice(**doc)

    async def find_by_id_and_org(self, voice_db_id: str, org_id: str) -> Optional[Voice]:
        """Find non-deleted voice by MongoDB _id scoped to organization."""
        try:
            object_id = ObjectId(voice_db_id)
        except (TypeError, ValueError, InvalidId):
            return None

        doc = await self.collection.find_one(
            {
                "_id": object_id,
                "organization_id": org_id,
                "deleted_at": None,
            }
        )
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return Voice(**doc)

    async def find_by_minimax_voice_id(self, voice_id: str, org_id: str) -> Optional[Voice]:
        """Find non-deleted voice by MiniMax voice_id scoped to organization."""
        doc = await self.collection.find_one(
            {
                "voice_id": voice_id,
                "organization_id": org_id,
                "deleted_at": None,
            }
        )
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return Voice(**doc)

    async def list_by_organization(
        self,
        org_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> VoiceListResult:
        """List non-deleted voices for an organization with total count."""
        query = {"organization_id": org_id, "deleted_at": None}
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        items: list[Voice] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(Voice(**doc))

        return VoiceListResult(items=items, total=total)

    async def list_by_creator_and_organization(
        self,
        org_id: str,
        created_by: str,
        skip: int = 0,
        limit: int = 20,
    ) -> VoiceListResult:
        """List non-deleted voices created by a user in an organization."""
        query = {
            "organization_id": org_id,
            "created_by": created_by,
            "deleted_at": None,
        }
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        items: list[Voice] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(Voice(**doc))

        return VoiceListResult(items=items, total=total)

    async def soft_delete(self, voice_db_id: str) -> bool:
        """Soft delete voice by setting deleted_at timestamp."""
        try:
            object_id = ObjectId(voice_db_id)
        except (TypeError, ValueError, InvalidId):
            return False

        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"_id": object_id, "deleted_at": None},
            {"$set": {"deleted_at": now}},
        )
        return result.modified_count > 0
