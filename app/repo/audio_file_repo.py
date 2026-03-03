"""Audio file repository for database operations."""

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.domain.models.audio_file import AudioFile


class AudioFileListResult(BaseModel):
    """Paginated audio file query result."""

    items: list[AudioFile]
    total: int


class AudioFileRepository:
    """Repository for generated audio metadata operations with soft delete support."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize AudioFileRepository with database instance."""
        self.collection = db.audio_files

    async def create(self, audio_data: dict[str, Any]) -> AudioFile:
        """Insert generated audio metadata into audio_files collection."""
        data = dict(audio_data)
        data.setdefault("created_at", datetime.now(timezone.utc))
        data.setdefault("deleted_at", None)

        result = await self.collection.insert_one(data)
        data["_id"] = str(result.inserted_id)
        return AudioFile(**data)

    async def find_by_id(self, audio_id: str) -> Optional[AudioFile]:
        """Find non-deleted audio by MongoDB _id."""
        try:
            object_id = ObjectId(audio_id)
        except (TypeError, ValueError, InvalidId):
            return None

        doc = await self.collection.find_one({"_id": object_id, "deleted_at": None})
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return AudioFile(**doc)

    async def find_by_id_and_org(self, audio_id: str, org_id: str) -> Optional[AudioFile]:
        """Find non-deleted audio by MongoDB _id scoped to organization."""
        try:
            object_id = ObjectId(audio_id)
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
        return AudioFile(**doc)

    async def list_by_organization(
        self,
        org_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> AudioFileListResult:
        """List non-deleted audio files for an organization with total count."""
        query = {"organization_id": org_id, "deleted_at": None}
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        items: list[AudioFile] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(AudioFile(**doc))

        return AudioFileListResult(items=items, total=total)

    async def list_by_creator_and_organization(
        self,
        org_id: str,
        created_by: str,
        skip: int = 0,
        limit: int = 20,
    ) -> AudioFileListResult:
        """List non-deleted audio files created by a user in an organization."""
        query = {
            "organization_id": org_id,
            "created_by": created_by,
            "deleted_at": None,
        }
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        items: list[AudioFile] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(AudioFile(**doc))

        return AudioFileListResult(items=items, total=total)

    async def soft_delete(self, audio_id: str) -> bool:
        """Soft delete audio file by setting deleted_at timestamp."""
        try:
            object_id = ObjectId(audio_id)
        except (TypeError, ValueError, InvalidId):
            return False

        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"_id": object_id, "deleted_at": None},
            {"$set": {"deleted_at": now}},
        )
        return result.modified_count > 0
