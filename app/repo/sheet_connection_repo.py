"""Sheet connection repository for database operations."""

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.models.sheet_connection import SheetConnection
from app.domain.schemas.sheet_crawler import (
    CreateConnectionRequest,
    UpdateConnectionRequest,
)


class SheetConnectionRepository:
    """Repository for sheet connection database operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize SheetConnectionRepository with database instance.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        self.collection = db.sheet_connections

    async def create(
        self,
        user_id: str,
        data: CreateConnectionRequest,
        organization_id: Optional[str] = None,
    ) -> SheetConnection:
        """Create a new sheet connection in database.

        Args:
            user_id: ID of the user creating the connection
            data: Connection creation request data

        Returns:
            Created SheetConnection instance
        """
        now = datetime.now(timezone.utc)
        connection_data = {
            "user_id": user_id,
            "organization_id": organization_id,
            "sheet_id": data.sheet_id,
            "sheet_name": data.sheet_name,
            "column_mappings": [m.model_dump() for m in data.column_mappings],
            "header_row": data.header_row,
            "data_start_row": data.data_start_row,
            "sync_enabled": True,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(connection_data)
        connection_data["_id"] = str(result.inserted_id)

        return SheetConnection(**connection_data)

    async def find_by_id(
        self,
        connection_id: str,
        organization_id: Optional[str] = None,
    ) -> Optional[SheetConnection]:
        """Find sheet connection by ID.

        Args:
            connection_id: Connection ID to search for

        Returns:
            SheetConnection instance if found, None otherwise
        """
        try:
            object_id = ObjectId(connection_id)
        except (TypeError, ValueError, InvalidId):
            return None

        query: dict = {"_id": object_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        doc = await self.collection.find_one(query)

        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return SheetConnection(**doc)

    async def find_by_user_id(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
    ) -> list[SheetConnection]:
        """Find all sheet connections for a user.

        Args:
            user_id: User ID to search for

        Returns:
            List of SheetConnection instances belonging to the user
        """
        query: dict = {"user_id": user_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        cursor = self.collection.find(query)
        connections = []

        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            connections.append(SheetConnection(**doc))

        return connections

    async def find_all_enabled(
        self,
        organization_id: Optional[str] = None,
    ) -> list[SheetConnection]:
        """Find all enabled sheet connections.

        Returns:
            List of all enabled SheetConnection instances
        """
        query: dict = {"sync_enabled": True}
        if organization_id is not None:
            query["organization_id"] = organization_id

        cursor = self.collection.find(query)
        connections = []

        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            connections.append(SheetConnection(**doc))

        return connections

    async def update(
        self,
        connection_id: str,
        data: UpdateConnectionRequest,
        organization_id: Optional[str] = None,
    ) -> Optional[SheetConnection]:
        """Update a sheet connection.

        Args:
            connection_id: Connection ID to update
            data: Update request data

        Returns:
            Updated SheetConnection instance if found, None otherwise
        """
        try:
            object_id = ObjectId(connection_id)
        except (TypeError, ValueError, InvalidId):
            return None

        update_data = {"updated_at": datetime.now(timezone.utc)}

        if data.sheet_name is not None:
            update_data["sheet_name"] = data.sheet_name
        if data.column_mappings is not None:
            update_data["column_mappings"] = [
                m.model_dump() for m in data.column_mappings
            ]
        if data.sync_enabled is not None:
            update_data["sync_enabled"] = data.sync_enabled

        query: dict = {"_id": object_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        result = await self.collection.find_one_and_update(
            query,
            {"$set": update_data},
            return_document=True,
        )

        if result is None:
            return None

        result["_id"] = str(result["_id"])
        return SheetConnection(**result)

    async def delete(
        self,
        connection_id: str,
        organization_id: Optional[str] = None,
    ) -> bool:
        """Delete a sheet connection.

        Args:
            connection_id: Connection ID to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            object_id = ObjectId(connection_id)
        except (TypeError, ValueError, InvalidId):
            return False

        query: dict = {"_id": object_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        result = await self.collection.delete_one(query)
        return result.deleted_count > 0
