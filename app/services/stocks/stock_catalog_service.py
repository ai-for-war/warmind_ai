"""Service layer for persisted stock catalog reads and manual refresh."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.models.stock import StockSymbol
from app.domain.schemas.stock import (
    StockListItem,
    StockListQuery,
    StockListResponse,
    StockRefreshResponse,
)
from app.repo.stock_symbol_repo import StockSymbolRepository
from app.services.stocks.cache import StockCatalogCache
from app.services.stocks.refresh import StockCatalogSnapshotRefresher


class StockCatalogService:
    """Coordinate stock catalog refresh, reads, and cache behavior."""

    def __init__(
        self,
        repository: StockSymbolRepository,
        refresher: StockCatalogSnapshotRefresher,
        cache: StockCatalogCache,
    ) -> None:
        self.repository = repository
        self.refresher = refresher
        self.cache = cache

    async def list_stocks(self, query: StockListQuery) -> StockListResponse:
        """Read one paginated stock catalog response."""
        if self._has_filters(query):
            items, total = await self.repository.find_filtered(
                q=query.q,
                exchange=query.exchange,
                group=query.group,
                page=query.page,
                page_size=query.page_size,
            )
            return self._build_response(
                items=items,
                total=total,
                page=query.page,
                page_size=query.page_size,
            )

        cached = await self.cache.get_page(page=query.page, page_size=query.page_size)
        if cached is not None:
            return cached

        items, total = await self.repository.list_paginated(
            page=query.page,
            page_size=query.page_size,
        )
        response = self._build_response(
            items=items,
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
        await self.cache.set_page(
            page=query.page,
            page_size=query.page_size,
            response=response,
        )
        return response

    async def refresh_catalog(self) -> StockRefreshResponse:
        """Refresh persisted stock catalog snapshot and invalidate default-list cache."""
        refresh_result = await self.refresher.refresh()
        await self.cache.invalidate_all()
        return StockRefreshResponse(
            status="success",
            source=refresh_result.source,
            upserted=refresh_result.upserted,
            updated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _has_filters(query: StockListQuery) -> bool:
        return any((query.q, query.exchange, query.group))

    @staticmethod
    def _build_response(
        *,
        items: list[StockSymbol],
        total: int,
        page: int,
        page_size: int,
    ) -> StockListResponse:
        return StockListResponse(
            items=[
                StockListItem(
                    symbol=item.symbol,
                    organ_name=item.organ_name,
                    exchange=item.exchange,
                    groups=item.groups,
                    industry_code=item.industry_code,
                    industry_name=item.industry_name,
                    source=item.source,
                    snapshot_at=item.snapshot_at,
                    updated_at=item.updated_at,
                )
                for item in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
