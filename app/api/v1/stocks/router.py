"""Stock catalog API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
    require_super_admin,
)
from app.common.service import get_stock_catalog_service
from app.domain.models.user import User
from app.domain.schemas.stock import (
    StockListQuery,
    StockListResponse,
    StockRefreshResponse,
)
from app.services.stocks.stock_catalog_service import StockCatalogService

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("", response_model=StockListResponse)
async def list_stocks(
    query: StockListQuery = Depends(),
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCatalogService = Depends(get_stock_catalog_service),
) -> StockListResponse:
    """List stock symbols from the persisted global stock catalog."""
    return await service.list_stocks(query)


@router.post(
    "/refresh",
    response_model=StockRefreshResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh_stock_catalog(
    _: User = Depends(require_super_admin),
    service: StockCatalogService = Depends(get_stock_catalog_service),
) -> StockRefreshResponse:
    """Refresh the persisted global stock catalog from vnstock."""
    return await service.refresh_catalog()
