from __future__ import annotations

import pytest

from app.common.exceptions import (
    DuplicateStockWatchlistNameError,
    StockSymbolNotFoundError,
    StockWatchlistItemNotFoundError,
    StockWatchlistNotFoundError,
)
from app.domain.schemas.stock_watchlist import (
    StockWatchlistAddItemRequest,
    StockWatchlistCreateRequest,
    StockWatchlistRenameRequest,
)
from app.services.stocks.watchlist_service import StockWatchlistService
from tests.support.watchlist_testkit import (
    InMemoryStockRepo,
    InMemoryWatchlistItemRepo,
    InMemoryWatchlistRepo,
    build_stock,
    build_user,
    utc,
)


@pytest.mark.asyncio
async def test_service_enforces_ownership_for_read_and_write_operations() -> None:
    watchlist_repo = InMemoryWatchlistRepo()
    item_repo = InMemoryWatchlistItemRepo()
    stock_repo = InMemoryStockRepo([build_stock(symbol="FPT", organ_name="FPT")])
    service = StockWatchlistService(watchlist_repo, item_repo, stock_repo)

    owner = build_user(user_id="owner-1")
    intruder = build_user(user_id="user-2")
    watchlist = await service.create_watchlist(
        current_user=owner,
        organization_id="org-1",
        request=StockWatchlistCreateRequest(name="Owner list"),
    )

    with pytest.raises(StockWatchlistNotFoundError):
        await service.list_watchlist_items(
            current_user=intruder,
            organization_id="org-1",
            watchlist_id=watchlist.id,
        )

    with pytest.raises(StockWatchlistNotFoundError):
        await service.rename_watchlist(
            current_user=intruder,
            organization_id="org-1",
            watchlist_id=watchlist.id,
            request=StockWatchlistRenameRequest(name="Intruder"),
        )


@pytest.mark.asyncio
async def test_add_item_rejects_unknown_stock_symbol() -> None:
    watchlist_repo = InMemoryWatchlistRepo()
    item_repo = InMemoryWatchlistItemRepo()
    stock_repo = InMemoryStockRepo()
    service = StockWatchlistService(watchlist_repo, item_repo, stock_repo)
    user = build_user()
    watchlist = await service.create_watchlist(
        current_user=user,
        organization_id="org-1",
        request=StockWatchlistCreateRequest(name="Tech"),
    )

    with pytest.raises(StockSymbolNotFoundError):
        await service.add_item(
            current_user=user,
            organization_id="org-1",
            watchlist_id=watchlist.id,
            request=StockWatchlistAddItemRequest(symbol="unknown"),
        )


@pytest.mark.asyncio
async def test_rename_watchlist_updates_name_and_rejects_duplicates() -> None:
    watchlist_repo = InMemoryWatchlistRepo()
    item_repo = InMemoryWatchlistItemRepo()
    stock_repo = InMemoryStockRepo()
    service = StockWatchlistService(watchlist_repo, item_repo, stock_repo)
    user = build_user()

    primary = await service.create_watchlist(
        current_user=user,
        organization_id="org-1",
        request=StockWatchlistCreateRequest(name="Tech"),
    )
    await service.create_watchlist(
        current_user=user,
        organization_id="org-1",
        request=StockWatchlistCreateRequest(name="Banks"),
    )

    renamed = await service.rename_watchlist(
        current_user=user,
        organization_id="org-1",
        watchlist_id=primary.id,
        request=StockWatchlistRenameRequest(name=" Growth "),
    )

    assert renamed.name == "Growth"

    with pytest.raises(DuplicateStockWatchlistNameError):
        await service.rename_watchlist(
            current_user=user,
            organization_id="org-1",
            watchlist_id=primary.id,
            request=StockWatchlistRenameRequest(name="banks"),
        )


@pytest.mark.asyncio
async def test_add_and_remove_item_behavior_round_trips_successfully() -> None:
    watchlist_repo = InMemoryWatchlistRepo()
    item_repo = InMemoryWatchlistItemRepo()
    stock_repo = InMemoryStockRepo([build_stock(symbol="fpt", organ_name="FPT")])
    service = StockWatchlistService(watchlist_repo, item_repo, stock_repo)
    user = build_user()
    watchlist = await service.create_watchlist(
        current_user=user,
        organization_id="org-1",
        request=StockWatchlistCreateRequest(name="Tech"),
    )

    added = await service.add_item(
        current_user=user,
        organization_id="org-1",
        watchlist_id=watchlist.id,
        request=StockWatchlistAddItemRequest(symbol="fpt"),
    )

    removed = await service.remove_item(
        current_user=user,
        organization_id="org-1",
        watchlist_id=watchlist.id,
        symbol=" fpt ",
    )

    assert added.symbol == "FPT"
    assert removed.symbol == "FPT"
    assert item_repo.count_for_watchlist(watchlist.id) == 0

    with pytest.raises(StockWatchlistItemNotFoundError):
        await service.remove_item(
            current_user=user,
            organization_id="org-1",
            watchlist_id=watchlist.id,
            symbol="FPT",
        )


@pytest.mark.asyncio
async def test_list_items_merges_latest_catalog_data_and_handles_missing_catalog_rows() -> None:
    watchlist_repo = InMemoryWatchlistRepo()
    item_repo = InMemoryWatchlistItemRepo()
    stock_repo = InMemoryStockRepo(
        [
            build_stock(
                symbol="FPT",
                organ_name="FPT Old",
                exchange="HOSE",
                groups=["VN30"],
                industry_code=8300,
                industry_name="Cong nghe cu",
                snapshot_at=utc(2026, 4, 12),
                updated_at=utc(2026, 4, 12, 1),
            ),
            build_stock(symbol="VCB", organ_name="VCB", exchange="HOSE"),
        ]
    )
    service = StockWatchlistService(watchlist_repo, item_repo, stock_repo)
    user = build_user()
    watchlist = await service.create_watchlist(
        current_user=user,
        organization_id="org-1",
        request=StockWatchlistCreateRequest(name="Mixed"),
    )
    await service.add_item(
        current_user=user,
        organization_id="org-1",
        watchlist_id=watchlist.id,
        request=StockWatchlistAddItemRequest(symbol="FPT"),
    )
    await service.add_item(
        current_user=user,
        organization_id="org-1",
        watchlist_id=watchlist.id,
        request=StockWatchlistAddItemRequest(symbol="VCB"),
    )

    stock_repo.set_stock(
        build_stock(
            symbol="FPT",
            organ_name="FPT Latest",
            exchange="HOSE",
            groups=["VN30", "VN100"],
            industry_code=8300,
            industry_name="Cong nghe moi",
            snapshot_at=utc(2026, 4, 18),
            updated_at=utc(2026, 4, 18, 1),
        )
    )
    stock_repo.remove_stock("VCB")

    response = await service.list_watchlist_items(
        current_user=user,
        organization_id="org-1",
        watchlist_id=watchlist.id,
    )

    assert [item.symbol for item in response.items] == ["VCB", "FPT"]
    assert response.items[0].stock is None
    assert response.items[1].stock.organ_name == "FPT Latest"
    assert response.items[1].stock.groups == ["VN30", "VN100"]


@pytest.mark.asyncio
async def test_delete_watchlist_cascades_saved_items() -> None:
    watchlist_repo = InMemoryWatchlistRepo()
    item_repo = InMemoryWatchlistItemRepo()
    stock_repo = InMemoryStockRepo([build_stock(symbol="FPT", organ_name="FPT")])
    service = StockWatchlistService(watchlist_repo, item_repo, stock_repo)
    user = build_user()
    watchlist = await service.create_watchlist(
        current_user=user,
        organization_id="org-1",
        request=StockWatchlistCreateRequest(name="Tech"),
    )
    await service.add_item(
        current_user=user,
        organization_id="org-1",
        watchlist_id=watchlist.id,
        request=StockWatchlistAddItemRequest(symbol="FPT"),
    )

    deleted = await service.delete_watchlist(
        current_user=user,
        organization_id="org-1",
        watchlist_id=watchlist.id,
    )

    assert deleted.deleted is True
    assert item_repo.count_for_watchlist(watchlist.id) == 0


@pytest.mark.asyncio
async def test_same_symbol_can_exist_in_different_watchlists_for_same_user_and_org() -> None:
    watchlist_repo = InMemoryWatchlistRepo()
    item_repo = InMemoryWatchlistItemRepo()
    stock_repo = InMemoryStockRepo([build_stock(symbol="FPT", organ_name="FPT")])
    service = StockWatchlistService(watchlist_repo, item_repo, stock_repo)
    user = build_user()

    first = await service.create_watchlist(
        current_user=user,
        organization_id="org-1",
        request=StockWatchlistCreateRequest(name="Tech"),
    )
    second = await service.create_watchlist(
        current_user=user,
        organization_id="org-1",
        request=StockWatchlistCreateRequest(name="Momentum"),
    )

    first_item = await service.add_item(
        current_user=user,
        organization_id="org-1",
        watchlist_id=first.id,
        request=StockWatchlistAddItemRequest(symbol="FPT"),
    )
    second_item = await service.add_item(
        current_user=user,
        organization_id="org-1",
        watchlist_id=second.id,
        request=StockWatchlistAddItemRequest(symbol="FPT"),
    )

    assert first_item.watchlist_id == first.id
    assert second_item.watchlist_id == second.id
    assert item_repo.count_for_watchlist(first.id) == 1
    assert item_repo.count_for_watchlist(second.id) == 1
