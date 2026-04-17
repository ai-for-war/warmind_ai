"""Repository for stock watchlist persistence operations."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING, ReturnDocument

from app.domain.models.stock_watchlist import StockWatchlist


class StockWatchlistRepository:
    """Database access wrapper for user-owned stock watchlists."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.stock_watchlists

    async def create(
        self,
        *,
        user_id: str,
        organization_id: str,
        name: str,
        normalized_name: str,
    ) -> StockWatchlist:
        """Create one watchlist document for a user in one organization."""
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": user_id,
            "organization_id": organization_id,
            "name": name,
            "normalized_name": normalized_name,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)
        return StockWatchlist(**payload)

    async def list_by_user_and_organization(
        self,
        *,
        user_id: str,
        organization_id: str,
    ) -> list[StockWatchlist]:
        """List one user's watchlists inside one organization."""
        cursor = self.collection.find(
            {
                "user_id": user_id,
                "organization_id": organization_id,
            }
        ).sort("updated_at", DESCENDING)
        documents = [document async for document in cursor]
        return [self._to_model(document) for document in documents]

    async def find_owned_watchlist(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
    ) -> StockWatchlist | None:
        """Find one owned watchlist by id and scope."""
        object_id = _parse_object_id(watchlist_id)
        if object_id is None:
            return None

        document = await self.collection.find_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
            }
        )
        return self._to_model(document)

    async def rename(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
        name: str,
        normalized_name: str,
    ) -> StockWatchlist | None:
        """Rename one owned watchlist and bump its updated timestamp."""
        object_id = _parse_object_id(watchlist_id)
        if object_id is None:
            return None

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
            },
            {
                "$set": {
                    "name": name,
                    "normalized_name": normalized_name,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def delete(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
    ) -> bool:
        """Delete one owned watchlist by id and scope."""
        object_id = _parse_object_id(watchlist_id)
        if object_id is None:
            return False

        result = await self.collection.delete_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
            }
        )
        return result.deleted_count > 0

    async def has_duplicate_name(
        self,
        *,
        user_id: str,
        organization_id: str,
        normalized_name: str,
        exclude_watchlist_id: str | None = None,
    ) -> bool:
        """Return whether one watchlist name already exists in the same scope."""
        query: dict[str, object] = {
            "user_id": user_id,
            "organization_id": organization_id,
            "normalized_name": normalized_name,
        }
        if exclude_watchlist_id is not None:
            object_id = _parse_object_id(exclude_watchlist_id)
            if object_id is not None:
                query["_id"] = {"$ne": object_id}

        return await self.collection.count_documents(query, limit=1) > 0

    @staticmethod
    def _to_model(document: dict[str, object] | None) -> StockWatchlist | None:
        """Convert one MongoDB document into a typed watchlist model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return StockWatchlist(**payload)


def _parse_object_id(value: str) -> ObjectId | None:
    """Parse one string id into ObjectId when valid."""
    try:
        return ObjectId(value)
    except (TypeError, ValueError, InvalidId):
        return None
