"""Stock catalog API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
    require_super_admin,
)
from app.common.service import get_stock_catalog_service, get_stock_company_service
from app.domain.models.user import User
from app.domain.schemas.stock import (
    StockListQuery,
    StockListResponse,
    StockRefreshResponse,
)
from app.domain.schemas.stock_company import (
    StockCompanyAffiliateResponse,
    StockCompanyEventsResponse,
    StockCompanyNewsResponse,
    StockCompanyOfficersQuery,
    StockCompanyOfficersResponse,
    StockCompanyOverviewResponse,
    StockCompanyRatioSummaryResponse,
    StockCompanyReportsResponse,
    StockCompanyShareholdersResponse,
    StockCompanySubsidiariesQuery,
    StockCompanySubsidiariesResponse,
    StockCompanyTradingStatsResponse,
)
from app.services.stocks.company_service import StockCompanyService
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


@router.get("/{symbol}/company/overview", response_model=StockCompanyOverviewResponse)
async def get_stock_company_overview(
    symbol: str,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanyOverviewResponse:
    """Return the company overview tab for one stock symbol."""
    return await service.get_overview(symbol)


@router.get(
    "/{symbol}/company/shareholders",
    response_model=StockCompanyShareholdersResponse,
)
async def get_stock_company_shareholders(
    symbol: str,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanyShareholdersResponse:
    """Return the shareholders tab for one stock symbol."""
    return await service.get_shareholders(symbol)


@router.get("/{symbol}/company/officers", response_model=StockCompanyOfficersResponse)
async def get_stock_company_officers(
    symbol: str,
    query: StockCompanyOfficersQuery = Depends(),
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanyOfficersResponse:
    """Return the officers tab for one stock symbol."""
    return await service.get_officers(symbol, filter_by=query.filter_by)


@router.get(
    "/{symbol}/company/subsidiaries",
    response_model=StockCompanySubsidiariesResponse,
)
async def get_stock_company_subsidiaries(
    symbol: str,
    query: StockCompanySubsidiariesQuery = Depends(),
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanySubsidiariesResponse:
    """Return the subsidiaries tab for one stock symbol."""
    return await service.get_subsidiaries(symbol, filter_by=query.filter_by)


@router.get("/{symbol}/company/affiliate", response_model=StockCompanyAffiliateResponse)
async def get_stock_company_affiliate(
    symbol: str,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanyAffiliateResponse:
    """Return the affiliate tab for one stock symbol."""
    return await service.get_affiliate(symbol)


@router.get("/{symbol}/company/events", response_model=StockCompanyEventsResponse)
async def get_stock_company_events(
    symbol: str,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanyEventsResponse:
    """Return the events tab for one stock symbol."""
    return await service.get_events(symbol)


@router.get("/{symbol}/company/news", response_model=StockCompanyNewsResponse)
async def get_stock_company_news(
    symbol: str,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanyNewsResponse:
    """Return the news tab for one stock symbol."""
    return await service.get_news(symbol)


@router.get("/{symbol}/company/reports", response_model=StockCompanyReportsResponse)
async def get_stock_company_reports(
    symbol: str,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanyReportsResponse:
    """Return the reports tab for one stock symbol."""
    return await service.get_reports(symbol)


@router.get(
    "/{symbol}/company/ratio-summary",
    response_model=StockCompanyRatioSummaryResponse,
)
async def get_stock_company_ratio_summary(
    symbol: str,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanyRatioSummaryResponse:
    """Return the ratio-summary tab for one stock symbol."""
    return await service.get_ratio_summary(symbol)


@router.get(
    "/{symbol}/company/trading-stats",
    response_model=StockCompanyTradingStatsResponse,
)
async def get_stock_company_trading_stats(
    symbol: str,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: StockCompanyService = Depends(get_stock_company_service),
) -> StockCompanyTradingStatsResponse:
    """Return the trading-stats tab for one stock symbol."""
    return await service.get_trading_stats(symbol)
