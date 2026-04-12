"""Repository for persisted stock symbol catalog documents."""

from __future__ import annotations

from datetime import datetime
import re

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, ReturnDocument, UpdateOne

from app.domain.models.stock import StockSymbol


class StockSymbolRepository:
    """Database access wrapper for stock symbol catalog persistence."""

    SNAPSHOT_META_ID = "active_snapshot"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.stock_symbols
        self.metadata_collection = db.stock_catalog_metadata

    async def upsert(self, stock_symbol: StockSymbol) -> StockSymbol:
        """Upsert one normalized stock symbol document keyed by symbol."""
        payload = stock_symbol.model_dump(by_alias=True)
        persisted = await self.collection.find_one_and_update(
            {"symbol": stock_symbol.symbol},
            {"$set": payload},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return StockSymbol(**persisted)

    async def list_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockSymbol], int]:
        """Return one unfiltered page of stock symbols sorted by symbol."""
        skip = (page - 1) * page_size
        query = await self._build_active_query()
        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort([("symbol", ASCENDING)])
            .skip(skip)
            .limit(page_size)
        )
        documents = [document async for document in cursor]
        return [StockSymbol(**document) for document in documents], total

    async def find_filtered(
        self,
        *,
        q: str | None = None,
        exchange: str | None = None,
        group: str | None = None,
        industry_code: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockSymbol], int]:
        """Return one filtered page of stock symbols plus total match count."""
        skip = (page - 1) * page_size
        query = await self._build_active_query(
            q=q,
            exchange=exchange,
            group=group,
            industry_code=industry_code,
        )
        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort([("symbol", ASCENDING)])
            .skip(skip)
            .limit(page_size)
        )
        documents = [document async for document in cursor]
        return [StockSymbol(**document) for document in documents], total

    async def count(
        self,
        *,
        q: str | None = None,
        exchange: str | None = None,
        group: str | None = None,
        industry_code: int | None = None,
    ) -> int:
        """Count stock symbols matching the supplied optional filters."""
        return await self.collection.count_documents(
            await self._build_active_query(
                q=q,
                exchange=exchange,
                group=group,
                industry_code=industry_code,
            )
        )

    async def replace_snapshot(
        self,
        snapshot: list[StockSymbol],
        *,
        snapshot_at: datetime,
    ) -> int:
        """Persist one full snapshot and atomically mark it active for reads."""
        operations = [
            UpdateOne(
                {"symbol": stock_symbol.symbol},
                {"$set": stock_symbol.model_dump(by_alias=True)},
                upsert=True,
            )
            for stock_symbol in snapshot
        ]
        if operations:
            await self.collection.bulk_write(operations, ordered=True)

        await self.metadata_collection.find_one_and_update(
            {"_id": self.SNAPSHOT_META_ID},
            {"$set": {"snapshot_at": snapshot_at}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        await self.collection.delete_many({"snapshot_at": {"$ne": snapshot_at}})
        return len(snapshot)

    async def _build_active_query(
        self,
        *,
        q: str | None = None,
        exchange: str | None = None,
        group: str | None = None,
        industry_code: int | None = None,
    ) -> dict[str, object]:
        query: dict[str, object] = {}
        active_snapshot_at = await self.get_active_snapshot_at()
        if active_snapshot_at is not None:
            query["snapshot_at"] = active_snapshot_at

        normalized_exchange = (exchange or "").strip().upper()
        if normalized_exchange:
            query["exchange"] = normalized_exchange

        normalized_group = (group or "").strip().upper()
        if normalized_group:
            query["groups"] = normalized_group

        if industry_code is not None:
            query["industry_code"] = industry_code

        normalized_query = (q or "").strip().lower()
        if normalized_query:
            pattern = re.escape(normalized_query)
            query["$or"] = [
                {"normalized_symbol": {"$regex": pattern, "$options": "i"}},
                {"normalized_organ_name": {"$regex": pattern, "$options": "i"}},
            ]

        return query

    async def get_active_snapshot_at(self) -> datetime | None:
        """Return the snapshot timestamp currently visible to read paths."""
        metadata = await self.metadata_collection.find_one({"_id": self.SNAPSHOT_META_ID})
        if not isinstance(metadata, dict):
            return None
        snapshot_at = metadata.get("snapshot_at")
        return snapshot_at if isinstance(snapshot_at, datetime) else None
