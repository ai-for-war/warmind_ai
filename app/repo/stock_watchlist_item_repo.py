"""Repository for stock watchlist item persistence operations."""

from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.domain.models.stock_watchlist import StockWatchlistItem


class StockWatchlistItemRepository:
    """Database access wrapper for saved stock symbols inside watchlists."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.stock_watchlist_items

    async def add(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
        symbol: str,
        normalized_symbol: str,
    ) -> StockWatchlistItem:
        """Persist one saved stock symbol inside a watchlist."""
        now = datetime.now(timezone.utc)
        payload = {
            "watchlist_id": watchlist_id,
            "user_id": user_id,
            "organization_id": organization_id,
            "symbol": symbol,
            "normalized_symbol": normalized_symbol,
            "saved_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)
        return StockWatchlistItem(**payload)

    async def list_by_watchlist(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
    ) -> list[StockWatchlistItem]:
        """List saved symbols in one watchlist ordered newest first."""
        cursor = self.collection.find(
            {
                "watchlist_id": watchlist_id,
                "user_id": user_id,
                "organization_id": organization_id,
            }
        ).sort("saved_at", DESCENDING)
        documents = [document async for document in cursor]
        return [self._to_model(document) for document in documents]

    async def remove_by_symbol(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
        normalized_symbol: str,
    ) -> bool:
        """Remove one saved symbol from one owned watchlist."""
        result = await self.collection.delete_one(
            {
                "watchlist_id": watchlist_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "normalized_symbol": normalized_symbol,
            }
        )
        return result.deleted_count > 0

    async def has_duplicate_symbol(
        self,
        *,
        watchlist_id: str,
        normalized_symbol: str,
    ) -> bool:
        """Return whether a symbol already exists in one watchlist."""
        return (
            await self.collection.count_documents(
                {
                    "watchlist_id": watchlist_id,
                    "normalized_symbol": normalized_symbol,
                },
                limit=1,
            )
            > 0
        )

    async def delete_by_watchlist(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
    ) -> int:
        """Delete all saved symbols belonging to one owned watchlist."""
        result = await self.collection.delete_many(
            {
                "watchlist_id": watchlist_id,
                "user_id": user_id,
                "organization_id": organization_id,
            }
        )
        return result.deleted_count

    @staticmethod
    def _to_model(document: dict[str, object]) -> StockWatchlistItem:
        """Convert one MongoDB document into a typed watchlist-item model."""
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return StockWatchlistItem(**payload)
