"""Repository for persisted stock symbol catalog documents."""

from __future__ import annotations

import re

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, ReturnDocument

from app.domain.models.stock import StockSymbol


class StockSymbolRepository:
    """Database access wrapper for stock symbol catalog persistence."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.stock_symbols

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
        total = await self.count()
        cursor = (
            self.collection.find({})
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
        query = self._build_query(
            q=q,
            exchange=exchange,
            group=group,
            industry_code=industry_code,
        )
        total = await self.count(
            q=q,
            exchange=exchange,
            group=group,
            industry_code=industry_code,
        )
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
            self._build_query(
                q=q,
                exchange=exchange,
                group=group,
                industry_code=industry_code,
            )
        )

    def _build_query(
        self,
        *,
        q: str | None,
        exchange: str | None,
        group: str | None,
        industry_code: int | None,
    ) -> dict[str, object]:
        query: dict[str, object] = {}

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
