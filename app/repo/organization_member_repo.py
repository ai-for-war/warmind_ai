"""Organization member repository for database operations."""

from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.models.organization import OrganizationMember, OrganizationRole


class OrganizationMemberRepository:
    """Repository for organization membership database operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize OrganizationMemberRepository with database instance."""
        self.collection = db.organization_members

    async def create(
        self,
        user_id: str,
        organization_id: str,
        added_by: str,
        role: OrganizationRole = OrganizationRole.USER,
        is_active: bool = True,
    ) -> OrganizationMember:
        """Create a new organization membership."""
        now = datetime.now(timezone.utc)
        member_data = {
            "user_id": user_id,
            "organization_id": organization_id,
            "role": role.value if isinstance(role, OrganizationRole) else role,
            "added_by": added_by,
            "is_active": is_active,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(member_data)
        member_data["_id"] = str(result.inserted_id)
        return OrganizationMember(**member_data)

    async def find_by_user_and_org(
        self,
        user_id: str,
        organization_id: str,
        *,
        is_active: Optional[bool] = None,
    ) -> Optional[OrganizationMember]:
        """Find membership by user and organization."""
        query: dict = {"user_id": user_id, "organization_id": organization_id}
        if is_active is not None:
            query["is_active"] = is_active

        doc = await self.collection.find_one(query)
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return OrganizationMember(**doc)

    async def list_by_organization(
        self,
        organization_id: str,
        *,
        is_active: Optional[bool] = None,
    ) -> list[OrganizationMember]:
        """List memberships by organization."""
        query: dict = {"organization_id": organization_id}
        if is_active is not None:
            query["is_active"] = is_active

        cursor = self.collection.find(query).sort("created_at", 1)
        members: list[OrganizationMember] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            members.append(OrganizationMember(**doc))

        return members

    async def list_by_user(
        self,
        user_id: str,
        *,
        is_active: Optional[bool] = None,
    ) -> list[OrganizationMember]:
        """List memberships by user."""
        query: dict = {"user_id": user_id}
        if is_active is not None:
            query["is_active"] = is_active

        cursor = self.collection.find(query).sort("created_at", 1)
        members: list[OrganizationMember] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            members.append(OrganizationMember(**doc))

        return members

    async def update_role(
        self,
        user_id: str,
        organization_id: str,
        role: OrganizationRole,
    ) -> Optional[OrganizationMember]:
        """Update role of a membership."""
        doc = await self.collection.find_one_and_update(
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "is_active": True,
            },
            {
                "$set": {
                    "role": role.value if isinstance(role, OrganizationRole) else role,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=True,
        )
        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return OrganizationMember(**doc)

    async def remove(self, user_id: str, organization_id: str) -> bool:
        """Soft delete membership by setting is_active to False."""
        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "is_active": True,
            },
            {"$set": {"is_active": False, "updated_at": now}},
        )
        return result.modified_count > 0
