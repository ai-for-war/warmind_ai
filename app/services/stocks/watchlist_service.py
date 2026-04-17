"""Service layer for user-owned stock watchlist CRUD and item reads."""

from __future__ import annotations

from app.common.exceptions import (
    DuplicateStockWatchlistItemError,
    DuplicateStockWatchlistNameError,
    StockSymbolNotFoundError,
    StockWatchlistItemNotFoundError,
    StockWatchlistNotFoundError,
)
from app.domain.models.stock import StockSymbol
from app.domain.models.stock_watchlist import StockWatchlist, StockWatchlistItem
from app.domain.models.user import User
from app.domain.schemas.stock_watchlist import (
    StockWatchlistAddItemRequest,
    StockWatchlistCreateRequest,
    StockWatchlistDeleteResponse,
    StockWatchlistItemResponse,
    StockWatchlistItemsResponse,
    StockWatchlistListResponse,
    StockWatchlistRemoveItemResponse,
    StockWatchlistRenameRequest,
    StockWatchlistStockMetadata,
    StockWatchlistSummary,
)
from app.repo.stock_symbol_repo import StockSymbolRepository
from app.repo.stock_watchlist_item_repo import StockWatchlistItemRepository
from app.repo.stock_watchlist_repo import StockWatchlistRepository


class StockWatchlistService:
    """Coordinate watchlist CRUD, ownership checks, and item composition."""

    def __init__(
        self,
        watchlist_repo: StockWatchlistRepository,
        item_repo: StockWatchlistItemRepository,
        stock_repo: StockSymbolRepository,
    ) -> None:
        self.watchlist_repo = watchlist_repo
        self.item_repo = item_repo
        self.stock_repo = stock_repo

    async def create_watchlist(
        self,
        *,
        current_user: User,
        organization_id: str,
        request: StockWatchlistCreateRequest,
    ) -> StockWatchlistSummary:
        name, normalized_name = self._normalize_watchlist_name(request.name)
        await self._ensure_unique_watchlist_name(
            user_id=current_user.id,
            organization_id=organization_id,
            normalized_name=normalized_name,
        )
        watchlist = await self.watchlist_repo.create(
            user_id=current_user.id,
            organization_id=organization_id,
            name=name,
            normalized_name=normalized_name,
        )
        return self._to_watchlist_summary(watchlist)

    async def list_watchlists(
        self,
        *,
        current_user: User,
        organization_id: str,
    ) -> StockWatchlistListResponse:
        watchlists = await self.watchlist_repo.list_by_user_and_organization(
            user_id=current_user.id,
            organization_id=organization_id,
        )
        return StockWatchlistListResponse(
            items=[self._to_watchlist_summary(watchlist) for watchlist in watchlists]
        )

    async def rename_watchlist(
        self,
        *,
        current_user: User,
        organization_id: str,
        watchlist_id: str,
        request: StockWatchlistRenameRequest,
    ) -> StockWatchlistSummary:
        watchlist = await self._get_owned_watchlist(
            watchlist_id=watchlist_id,
            current_user=current_user,
            organization_id=organization_id,
        )
        name, normalized_name = self._normalize_watchlist_name(request.name)
        if normalized_name != watchlist.normalized_name:
            await self._ensure_unique_watchlist_name(
                user_id=current_user.id,
                organization_id=organization_id,
                normalized_name=normalized_name,
                exclude_watchlist_id=watchlist.id,
            )

        renamed = await self.watchlist_repo.rename(
            watchlist_id=watchlist.id,
            user_id=current_user.id,
            organization_id=organization_id,
            name=name,
            normalized_name=normalized_name,
        )
        if renamed is None:
            raise StockWatchlistNotFoundError()
        return self._to_watchlist_summary(renamed)

    async def delete_watchlist(
        self,
        *,
        current_user: User,
        organization_id: str,
        watchlist_id: str,
    ) -> StockWatchlistDeleteResponse:
        watchlist = await self._get_owned_watchlist(
            watchlist_id=watchlist_id,
            current_user=current_user,
            organization_id=organization_id,
        )
        await self.item_repo.delete_by_watchlist(
            watchlist_id=watchlist.id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        deleted = await self.watchlist_repo.delete(
            watchlist_id=watchlist.id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        if not deleted:
            raise StockWatchlistNotFoundError()
        return StockWatchlistDeleteResponse(id=watchlist.id, deleted=True)

    async def list_watchlist_items(
        self,
        *,
        current_user: User,
        organization_id: str,
        watchlist_id: str,
    ) -> StockWatchlistItemsResponse:
        watchlist = await self._get_owned_watchlist(
            watchlist_id=watchlist_id,
            current_user=current_user,
            organization_id=organization_id,
        )
        items = await self.item_repo.list_by_watchlist(
            watchlist_id=watchlist.id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        stocks_by_symbol = await self._get_stock_map([item.symbol for item in items])
        return StockWatchlistItemsResponse(
            watchlist=self._to_watchlist_summary(watchlist),
            items=[
                self._to_item_response(item, stocks_by_symbol.get(item.symbol))
                for item in items
            ],
        )

    async def add_item(
        self,
        *,
        current_user: User,
        organization_id: str,
        watchlist_id: str,
        request: StockWatchlistAddItemRequest,
    ) -> StockWatchlistItemResponse:
        watchlist = await self._get_owned_watchlist(
            watchlist_id=watchlist_id,
            current_user=current_user,
            organization_id=organization_id,
        )
        symbol, normalized_symbol = self._normalize_symbol(request.symbol)
        stock = await self._get_required_stock(symbol)
        if await self.item_repo.has_duplicate_symbol(
            watchlist_id=watchlist.id,
            normalized_symbol=normalized_symbol,
        ):
            raise DuplicateStockWatchlistItemError()

        item = await self.item_repo.add(
            watchlist_id=watchlist.id,
            user_id=current_user.id,
            organization_id=organization_id,
            symbol=symbol,
            normalized_symbol=normalized_symbol,
        )
        return self._to_item_response(item, stock)

    async def remove_item(
        self,
        *,
        current_user: User,
        organization_id: str,
        watchlist_id: str,
        symbol: str,
    ) -> StockWatchlistRemoveItemResponse:
        watchlist = await self._get_owned_watchlist(
            watchlist_id=watchlist_id,
            current_user=current_user,
            organization_id=organization_id,
        )
        normalized_symbol_value, normalized_symbol = self._normalize_symbol(symbol)
        removed = await self.item_repo.remove_by_symbol(
            watchlist_id=watchlist.id,
            user_id=current_user.id,
            organization_id=organization_id,
            normalized_symbol=normalized_symbol,
        )
        if not removed:
            raise StockWatchlistItemNotFoundError()
        return StockWatchlistRemoveItemResponse(
            watchlist_id=watchlist.id,
            symbol=normalized_symbol_value,
            removed=True,
        )

    async def _get_owned_watchlist(
        self,
        *,
        watchlist_id: str,
        current_user: User,
        organization_id: str,
    ) -> StockWatchlist:
        watchlist = await self.watchlist_repo.find_owned_watchlist(
            watchlist_id=watchlist_id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        if watchlist is None:
            raise StockWatchlistNotFoundError()
        return watchlist

    async def _ensure_unique_watchlist_name(
        self,
        *,
        user_id: str,
        organization_id: str,
        normalized_name: str,
        exclude_watchlist_id: str | None = None,
    ) -> None:
        if await self.watchlist_repo.has_duplicate_name(
            user_id=user_id,
            organization_id=organization_id,
            normalized_name=normalized_name,
            exclude_watchlist_id=exclude_watchlist_id,
        ):
            raise DuplicateStockWatchlistNameError()

    async def _get_required_stock(self, symbol: str) -> StockSymbol:
        stocks = await self.stock_repo.find_active_by_symbols([symbol])
        if not stocks:
            raise StockSymbolNotFoundError()
        return stocks[0]

    async def _get_stock_map(self, symbols: list[str]) -> dict[str, StockSymbol]:
        stocks = await self.stock_repo.find_active_by_symbols(symbols)
        return {stock.symbol: stock for stock in stocks}

    @staticmethod
    def _normalize_watchlist_name(name: str) -> tuple[str, str]:
        normalized_name = name.strip()
        return normalized_name, normalized_name.lower()

    @staticmethod
    def _normalize_symbol(symbol: str) -> tuple[str, str]:
        normalized_symbol = symbol.strip().upper()
        return normalized_symbol, normalized_symbol.lower()

    @staticmethod
    def _to_watchlist_summary(watchlist: StockWatchlist) -> StockWatchlistSummary:
        return StockWatchlistSummary(
            id=watchlist.id,
            user_id=watchlist.user_id,
            organization_id=watchlist.organization_id,
            name=watchlist.name,
            created_at=watchlist.created_at,
            updated_at=watchlist.updated_at,
        )

    @staticmethod
    def _to_item_response(
        item: StockWatchlistItem,
        stock: StockSymbol | None,
    ) -> StockWatchlistItemResponse:
        return StockWatchlistItemResponse(
            id=item.id,
            watchlist_id=item.watchlist_id,
            user_id=item.user_id,
            organization_id=item.organization_id,
            symbol=item.symbol,
            saved_at=item.saved_at,
            updated_at=item.updated_at,
            stock=StockWatchlistService._to_stock_metadata(stock),
        )

    @staticmethod
    def _to_stock_metadata(
        stock: StockSymbol | None,
    ) -> StockWatchlistStockMetadata | None:
        if stock is None:
            return None
        return StockWatchlistStockMetadata(
            symbol=stock.symbol,
            organ_name=stock.organ_name,
            exchange=stock.exchange,
            groups=stock.groups,
            industry_code=stock.industry_code,
            industry_name=stock.industry_name,
            source=stock.source,
            snapshot_at=stock.snapshot_at,
            updated_at=stock.updated_at,
        )
