"""Stock watchlist API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.service import get_stock_watchlist_service
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
    StockWatchlistSummary,
)
from app.services.stocks.watchlist_service import StockWatchlistService

router = APIRouter(prefix="/stocks/watchlists", tags=["stocks"])


@router.post("", response_model=StockWatchlistSummary, status_code=status.HTTP_201_CREATED)
async def create_stock_watchlist(
    request: StockWatchlistCreateRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockWatchlistService = Depends(get_stock_watchlist_service),
) -> StockWatchlistSummary:
    """Create one named stock watchlist in the current organization scope."""
    return await service.create_watchlist(
        current_user=current_user,
        organization_id=org_context.organization_id,
        request=request,
    )


@router.get("", response_model=StockWatchlistListResponse)
async def list_stock_watchlists(
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockWatchlistService = Depends(get_stock_watchlist_service),
) -> StockWatchlistListResponse:
    """List the current user's stock watchlists in one organization scope."""
    return await service.list_watchlists(
        current_user=current_user,
        organization_id=org_context.organization_id,
    )


@router.patch("/{watchlist_id}", response_model=StockWatchlistSummary)
async def rename_stock_watchlist(
    watchlist_id: str,
    request: StockWatchlistRenameRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockWatchlistService = Depends(get_stock_watchlist_service),
) -> StockWatchlistSummary:
    """Rename one owned stock watchlist."""
    return await service.rename_watchlist(
        current_user=current_user,
        organization_id=org_context.organization_id,
        watchlist_id=watchlist_id,
        request=request,
    )


@router.delete("/{watchlist_id}", response_model=StockWatchlistDeleteResponse)
async def delete_stock_watchlist(
    watchlist_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockWatchlistService = Depends(get_stock_watchlist_service),
) -> StockWatchlistDeleteResponse:
    """Delete one owned stock watchlist and its saved items."""
    return await service.delete_watchlist(
        current_user=current_user,
        organization_id=org_context.organization_id,
        watchlist_id=watchlist_id,
    )


@router.get("/{watchlist_id}/items", response_model=StockWatchlistItemsResponse)
async def list_stock_watchlist_items(
    watchlist_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockWatchlistService = Depends(get_stock_watchlist_service),
) -> StockWatchlistItemsResponse:
    """List newest-first saved stock symbols for one owned watchlist."""
    return await service.list_watchlist_items(
        current_user=current_user,
        organization_id=org_context.organization_id,
        watchlist_id=watchlist_id,
    )


@router.post(
    "/{watchlist_id}/items",
    response_model=StockWatchlistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_stock_watchlist_item(
    watchlist_id: str,
    request: StockWatchlistAddItemRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockWatchlistService = Depends(get_stock_watchlist_service),
) -> StockWatchlistItemResponse:
    """Add one stock symbol to one owned watchlist."""
    return await service.add_item(
        current_user=current_user,
        organization_id=org_context.organization_id,
        watchlist_id=watchlist_id,
        request=request,
    )


@router.delete(
    "/{watchlist_id}/items/{symbol}",
    response_model=StockWatchlistRemoveItemResponse,
)
async def remove_stock_watchlist_item(
    watchlist_id: str,
    symbol: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockWatchlistService = Depends(get_stock_watchlist_service),
) -> StockWatchlistRemoveItemResponse:
    """Remove one stock symbol from one owned watchlist."""
    return await service.remove_item(
        current_user=current_user,
        organization_id=org_context.organization_id,
        watchlist_id=watchlist_id,
        symbol=symbol,
    )
