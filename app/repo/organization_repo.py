"""Organization repository for database operations."""

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.models.organization import Organization


class OrganizationRepository:
    """Repository for organization database operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize OrganizationRepository with database instance."""
        self.collection = db.organizations

    async def create(
        self,
        name: str,
        slug: str,
        created_by: str,
        description: Optional[str] = None,
        is_active: bool = True,
    ) -> Organization:
        """Create a new organization in database."""
        now = datetime.now(timezone.utc)
        org_data = {
            "name": name,
            "slug": slug,
            "description": description,
            "is_active": is_active,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(org_data)
        org_data["_id"] = str(result.inserted_id)
        return Organization(**org_data)

    async def find_by_id(self, organization_id: str) -> Optional[Organization]:
        """Find organization by ID."""
        try:
            object_id = ObjectId(organization_id)
        except (TypeError, ValueError, InvalidId):
            return None

        doc = await self.collection.find_one({"_id": object_id})
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return Organization(**doc)

    async def find_by_slug(self, slug: str) -> Optional[Organization]:
        """Find organization by slug."""
        doc = await self.collection.find_one({"slug": slug})
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return Organization(**doc)

    async def list_all(
        self,
        *,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Organization]:
        """List organizations with optional active-state filtering."""
        query: dict = {}
        if is_active is not None:
            query["is_active"] = is_active

        cursor = (
            self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        )

        organizations: list[Organization] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            organizations.append(Organization(**doc))

        return organizations

    async def update(
        self,
        organization_id: str,
        *,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Organization]:
        """Update organization fields."""
        try:
            object_id = ObjectId(organization_id)
        except (TypeError, ValueError, InvalidId):
            return None

        update_data = {"updated_at": datetime.now(timezone.utc)}
        if name is not None:
            update_data["name"] = name
        if slug is not None:
            update_data["slug"] = slug
        if description is not None:
            update_data["description"] = description
        if is_active is not None:
            update_data["is_active"] = is_active

        doc = await self.collection.find_one_and_update(
            {"_id": object_id},
            {"$set": update_data},
            return_document=True,
        )
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return Organization(**doc)

    async def deactivate(self, organization_id: str) -> bool:
        """Soft delete organization by setting is_active to False."""
        try:
            object_id = ObjectId(organization_id)
        except (TypeError, ValueError, InvalidId):
            return False

        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"_id": object_id, "is_active": True},
            {"$set": {"is_active": False, "updated_at": now}},
        )
        return result.modified_count > 0
