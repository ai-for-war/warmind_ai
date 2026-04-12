"""Manual stock catalog refresh flow built on vnstock VCI listings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.repo.stock_symbol_repo import StockSymbolRepository
from app.services.stocks.normalizer import build_stock_symbol_snapshot
from app.services.stocks.vnstock_gateway import (
    SUPPORTED_STOCK_GROUPS,
    VnstockListingGateway,
)


@dataclass(slots=True)
class StockCatalogRefreshResult:
    """Summary returned after persisting one stock catalog snapshot."""

    source: str
    upserted: int


class StockCatalogSnapshotRefresher:
    """Fetch, normalize, and persist one stock catalog snapshot."""

    def __init__(
        self,
        gateway: VnstockListingGateway,
        repository: StockSymbolRepository,
    ) -> None:
        self.gateway = gateway
        self.repository = repository

    async def refresh(self) -> StockCatalogRefreshResult:
        """Refresh the stock catalog by upserting normalized symbol documents."""
        snapshot_at = datetime.now(timezone.utc)
        snapshot = build_stock_symbol_snapshot(
            all_symbols=self.gateway.fetch_all_symbols(),
            symbols_by_exchange=self.gateway.fetch_symbols_by_exchange(),
            symbols_by_industries=self.gateway.fetch_symbols_by_industries(),
            group_memberships=self.gateway.fetch_group_memberships(
                SUPPORTED_STOCK_GROUPS
            ),
            source=self.gateway.SOURCE,
            now=snapshot_at,
        )
        upserted = await self.repository.replace_snapshot(
            snapshot,
            snapshot_at=snapshot_at,
        )

        return StockCatalogRefreshResult(
            source=self.gateway.SOURCE,
            upserted=upserted,
        )
