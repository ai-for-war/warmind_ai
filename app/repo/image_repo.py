"""Image repository for database operations."""

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.domain.models.image import Image


class ImageListResult(BaseModel):
    """Paginated image query result."""

    items: list[Image]
    total: int


class ImageRepository:
    """Repository for image metadata operations with soft delete support."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize ImageRepository with database instance."""
        self.collection = db.images

    async def create(self, image_data: dict[str, Any]) -> Image:
        """Insert image metadata into images collection."""
        data = dict(image_data)
        data.setdefault("created_at", datetime.now(timezone.utc))
        data.setdefault("deleted_at", None)

        result = await self.collection.insert_one(data)
        data["_id"] = str(result.inserted_id)
        return Image(**data)

    async def find_by_id(self, image_id: str) -> Optional[Image]:
        """Find non-deleted image by ID."""
        try:
            object_id = ObjectId(image_id)
        except (TypeError, ValueError, InvalidId):
            return None

        doc = await self.collection.find_one(
            {
                "_id": object_id,
                "deleted_at": None,
            }
        )
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return Image(**doc)

    async def find_by_id_and_org(self, image_id: str, org_id: str) -> Optional[Image]:
        """Find non-deleted image by ID scoped to organization."""
        try:
            object_id = ObjectId(image_id)
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
        return Image(**doc)

    async def list_by_organization(
        self,
        org_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> ImageListResult:
        """List non-deleted images for an organization with total count."""
        query = {
            "organization_id": org_id,
            "deleted_at": None,
        }

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        items: list[Image] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(Image(**doc))

        return ImageListResult(items=items, total=total)

    async def soft_delete(self, image_id: str) -> bool:
        """Soft delete image by setting deleted_at timestamp."""
        try:
            object_id = ObjectId(image_id)
        except (TypeError, ValueError, InvalidId):
            return False

        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {
                "_id": object_id,
                "deleted_at": None,
            },
            {"$set": {"deleted_at": now}},
        )
        return result.modified_count > 0

