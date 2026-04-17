from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

from bson import ObjectId

from app.domain.models.organization import OrganizationRole
from app.domain.models.stock import StockSymbol
from app.domain.models.stock_watchlist import StockWatchlist, StockWatchlistItem
from app.domain.models.user import User, UserRole


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def build_user(
    *,
    user_id: str = "user-1",
    role: UserRole = UserRole.USER,
) -> User:
    now = utc(2026, 1, 1)
    return User(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def build_stock(
    *,
    symbol: str,
    organ_name: str | None = None,
    exchange: str | None = None,
    groups: list[str] | None = None,
    industry_code: int | None = None,
    industry_name: str | None = None,
    snapshot_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> StockSymbol:
    stock_snapshot_at = snapshot_at or utc(2026, 4, 12)
    stock_updated_at = updated_at or utc(2026, 4, 12, 1)
    return StockSymbol(
        symbol=symbol,
        organ_name=organ_name,
        exchange=exchange,
        groups=groups or [],
        industry_code=industry_code,
        industry_name=industry_name,
        snapshot_at=stock_snapshot_at,
        updated_at=stock_updated_at,
    )


class InMemoryWatchlistRepo:
    def __init__(self) -> None:
        self._watchlists: dict[str, StockWatchlist] = {}
        self._counter = count()

    async def create(
        self,
        *,
        user_id: str,
        organization_id: str,
        name: str,
        normalized_name: str,
    ) -> StockWatchlist:
        timestamp = self._next_timestamp()
        watchlist = StockWatchlist(
            _id=str(ObjectId()),
            user_id=user_id,
            organization_id=organization_id,
            name=name,
            normalized_name=normalized_name,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._watchlists[watchlist.id] = watchlist
        return watchlist

    async def list_by_user_and_organization(
        self,
        *,
        user_id: str,
        organization_id: str,
    ) -> list[StockWatchlist]:
        return sorted(
            [
                watchlist
                for watchlist in self._watchlists.values()
                if watchlist.user_id == user_id
                and watchlist.organization_id == organization_id
            ],
            key=lambda item: item.updated_at,
            reverse=True,
        )

    async def find_owned_watchlist(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
    ) -> StockWatchlist | None:
        watchlist = self._watchlists.get(watchlist_id)
        if watchlist is None:
            return None
        if watchlist.user_id != user_id or watchlist.organization_id != organization_id:
            return None
        return watchlist

    async def rename(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
        name: str,
        normalized_name: str,
    ) -> StockWatchlist | None:
        watchlist = await self.find_owned_watchlist(
            watchlist_id=watchlist_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        if watchlist is None:
            return None
        renamed = watchlist.model_copy(
            update={
                "name": name,
                "normalized_name": normalized_name,
                "updated_at": self._next_timestamp(),
            }
        )
        self._watchlists[watchlist_id] = renamed
        return renamed

    async def delete(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
    ) -> bool:
        watchlist = await self.find_owned_watchlist(
            watchlist_id=watchlist_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        if watchlist is None:
            return False
        del self._watchlists[watchlist_id]
        return True

    async def has_duplicate_name(
        self,
        *,
        user_id: str,
        organization_id: str,
        normalized_name: str,
        exclude_watchlist_id: str | None = None,
    ) -> bool:
        return any(
            watchlist.user_id == user_id
            and watchlist.organization_id == organization_id
            and watchlist.normalized_name == normalized_name
            and watchlist.id != exclude_watchlist_id
            for watchlist in self._watchlists.values()
        )

    def _next_timestamp(self) -> datetime:
        return utc(2026, 4, 17) + timedelta(seconds=next(self._counter))


class InMemoryWatchlistItemRepo:
    def __init__(self) -> None:
        self._items: dict[str, StockWatchlistItem] = {}
        self._counter = count()

    async def add(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
        symbol: str,
        normalized_symbol: str,
    ) -> StockWatchlistItem:
        timestamp = self._next_timestamp()
        item = StockWatchlistItem(
            _id=str(ObjectId()),
            watchlist_id=watchlist_id,
            user_id=user_id,
            organization_id=organization_id,
            symbol=symbol,
            normalized_symbol=normalized_symbol,
            saved_at=timestamp,
            updated_at=timestamp,
        )
        self._items[item.id] = item
        return item

    async def list_by_watchlist(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
    ) -> list[StockWatchlistItem]:
        return sorted(
            [
                item
                for item in self._items.values()
                if item.watchlist_id == watchlist_id
                and item.user_id == user_id
                and item.organization_id == organization_id
            ],
            key=lambda item: item.saved_at,
            reverse=True,
        )

    async def remove_by_symbol(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
        normalized_symbol: str,
    ) -> bool:
        for item_id, item in list(self._items.items()):
            if (
                item.watchlist_id == watchlist_id
                and item.user_id == user_id
                and item.organization_id == organization_id
                and item.normalized_symbol == normalized_symbol
            ):
                del self._items[item_id]
                return True
        return False

    async def has_duplicate_symbol(
        self,
        *,
        watchlist_id: str,
        normalized_symbol: str,
    ) -> bool:
        return any(
            item.watchlist_id == watchlist_id
            and item.normalized_symbol == normalized_symbol
            for item in self._items.values()
        )

    async def delete_by_watchlist(
        self,
        *,
        watchlist_id: str,
        user_id: str,
        organization_id: str,
    ) -> int:
        deleted_count = 0
        for item_id, item in list(self._items.items()):
            if (
                item.watchlist_id == watchlist_id
                and item.user_id == user_id
                and item.organization_id == organization_id
            ):
                del self._items[item_id]
                deleted_count += 1
        return deleted_count

    def count_for_watchlist(self, watchlist_id: str) -> int:
        return sum(1 for item in self._items.values() if item.watchlist_id == watchlist_id)

    def _next_timestamp(self) -> datetime:
        return utc(2026, 4, 17) + timedelta(minutes=next(self._counter))


class InMemoryStockRepo:
    def __init__(self, stocks: list[StockSymbol] | None = None) -> None:
        self._stocks: dict[str, StockSymbol] = {}
        for stock in stocks or []:
            self._stocks[stock.symbol] = stock
        self.find_active_by_symbols_calls: list[list[str]] = []

    async def find_active_by_symbols(self, symbols: list[str]) -> list[StockSymbol]:
        self.find_active_by_symbols_calls.append(list(symbols))
        normalized = sorted(
            {
                symbol.strip().upper()
                for symbol in symbols
                if isinstance(symbol, str) and symbol.strip()
            }
        )
        return [self._stocks[symbol] for symbol in normalized if symbol in self._stocks]

    def set_stock(self, stock: StockSymbol) -> None:
        self._stocks[stock.symbol] = stock

    def remove_stock(self, symbol: str) -> None:
        self._stocks.pop(symbol.strip().upper(), None)


class FakeOrganization:
    def __init__(self, *, is_active: bool = True) -> None:
        self.is_active = is_active


class FakeOrganizationRepo:
    def __init__(self, active_org_ids: set[str] | None = None) -> None:
        self.active_org_ids = {"org-1"} if active_org_ids is None else active_org_ids

    async def find_by_id(self, organization_id: str):
        if organization_id in self.active_org_ids:
            return FakeOrganization(is_active=True)
        return None


class FakeMembership:
    def __init__(self, *, role: str = OrganizationRole.USER.value) -> None:
        self.role = role


class FakeMemberRepo:
    def __init__(self, memberships: set[tuple[str, str]] | None = None) -> None:
        self.memberships = {("user-1", "org-1")} if memberships is None else memberships

    async def find_by_user_and_org(
        self,
        *,
        user_id: str,
        organization_id: str,
        is_active: bool,
    ):
        del is_active
        if (user_id, organization_id) in self.memberships:
            return FakeMembership()
        return None
