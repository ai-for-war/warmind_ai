"""Sheet sync state repository for database operations."""

from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.models.sheet_connection import SheetSyncState
from app.domain.schemas.sheet_crawler import SyncStatus


class SheetSyncStateRepository:
    """Repository for sheet sync state database operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize SheetSyncStateRepository with database instance.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        self.collection = db.sheet_sync_states

    async def find_by_connection_id(
        self, connection_id: str
    ) -> Optional[SheetSyncState]:
        """Find sync state by connection ID.

        Args:
            connection_id: Connection ID to search for

        Returns:
            SheetSyncState instance if found, None otherwise
        """
        doc = await self.collection.find_one({"connection_id": connection_id})

        if doc is None:
            return None

        doc["_id"] = str(doc["_id"])
        return SheetSyncState(**doc)

    async def update_state(
        self,
        connection_id: str,
        last_synced_row: int,
        status: SyncStatus,
        total_rows_synced: int,
        error_message: Optional[str] = None,
    ) -> SheetSyncState:
        """Update or create sync state for a connection.

        Args:
            connection_id: Connection ID to update
            last_synced_row: Last synced row number
            status: Current sync status
            total_rows_synced: Total number of rows synced
            error_message: Error message if sync failed

        Returns:
            Updated or created SheetSyncState instance
        """
        now = datetime.now(timezone.utc)

        update_data = {
            "connection_id": connection_id,
            "last_synced_row": last_synced_row,
            "status": status.value if isinstance(status, SyncStatus) else status,
            "total_rows_synced": total_rows_synced,
            "error_message": error_message,
            "last_sync_time": now,
            "updated_at": now,
        }

        result = await self.collection.find_one_and_update(
            {"connection_id": connection_id},
            {
                "$set": update_data,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            return_document=True,
        )

        result["_id"] = str(result["_id"])
        return SheetSyncState(**result)

    async def delete_by_connection_id(self, connection_id: str) -> int:
        """Delete sync state by connection ID.

        Args:
            connection_id: Connection ID to delete sync state for

        Returns:
            Number of documents deleted
        """
        result = await self.collection.delete_many({"connection_id": connection_id})
        return result.deleted_count
