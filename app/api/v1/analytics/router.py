"""Analytics API router.

Provides endpoints for retrieving analytics data from synced Google Sheets.
Supports summary metrics, time series, distribution, top N, and paginated data.
"""

import logging
from datetime import date
from typing import Optional, Union

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_active_user
from app.common.service import get_analytics_service
from app.domain.models.user import User
from app.domain.schemas.analytics import (
    DataResponse,
    DistributionResponse,
    Granularity,
    OrderItemsSummaryResponse,
    OrdersSummaryResponse,
    SimpleSummaryResponse,
    SortOrder,
    TimeSeriesMetrics,
    TimeSeriesResponse,
    TopMetric,
    TopResponse,
)
from app.services.analytics.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Type alias for summary response union
SummaryResponse = Union[
    OrdersSummaryResponse, OrderItemsSummaryResponse, SimpleSummaryResponse
]


@router.get(
    "/{connection_id}/summary",
    response_model=SummaryResponse,
)
async def get_summary(
    connection_id: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> dict:
    """Get summary metrics for a connection.

    Returns summary metrics appropriate for the detected sheet type:
    - Orders: total_count, total_amount, avg_amount
    - Order Items: total_quantity, total_line_total, unique_products
    - Customers/Products: total_count

    Args:
        connection_id: Connection ID
        date_from: Optional start date filter (orders only)
        date_to: Optional end date filter (orders only)
        current_user: Authenticated user
        analytics_service: Analytics service instance

    Returns:
        Summary metrics for the connection

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
        HTTPException: 400 if date_from > date_to
    """
    return await analytics_service.get_summary(
        connection_id=connection_id,
        user_id=current_user.id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/{connection_id}/time-series",
    response_model=TimeSeriesResponse,
)
async def get_time_series(
    connection_id: str,
    date_from: date,
    date_to: date,
    granularity: Granularity = Granularity.DAY,
    metrics: TimeSeriesMetrics = TimeSeriesMetrics.BOTH,
    current_user: User = Depends(get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> dict:
    """Get time series data for orders sheet.

    Returns data grouped by the specified granularity (day/week/month/year).
    Only supported for orders sheet type.

    Args:
        connection_id: Connection ID
        date_from: Start date (required)
        date_to: End date (required)
        granularity: Time grouping granularity (default: day)
        metrics: Which metrics to include (count/amount/both)
        current_user: Authenticated user
        analytics_service: Analytics service instance

    Returns:
        Time series data with granularity and data points

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
        HTTPException: 400 if sheet type doesn't support time series
        HTTPException: 400 if date_from > date_to
    """
    return await analytics_service.get_time_series(
        connection_id=connection_id,
        user_id=current_user.id,
        date_from=date_from,
        date_to=date_to,
        granularity=granularity,
        metrics=metrics,
    )


@router.get(
    "/{connection_id}/distribution/{field}",
    response_model=DistributionResponse,
)
async def get_distribution(
    connection_id: str,
    field: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> dict:
    """Get distribution data for a field.

    Returns count and percentage for each unique value of the field.
    Only supported for orders sheet type with fields: platform, order_status.

    Args:
        connection_id: Connection ID
        field: Field to get distribution for (platform, order_status)
        date_from: Optional start date filter
        date_to: Optional end date filter
        current_user: Authenticated user
        analytics_service: Analytics service instance

    Returns:
        Distribution data with field name and data points

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
        HTTPException: 400 if sheet type doesn't support distribution
        HTTPException: 400 if field not supported for this sheet type
        HTTPException: 400 if date_from > date_to
    """
    return await analytics_service.get_distribution(
        connection_id=connection_id,
        user_id=current_user.id,
        field=field,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/{connection_id}/top/{field}",
    response_model=TopResponse,
)
async def get_top(
    connection_id: str,
    field: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(default=10, ge=1, le=50),
    metric: TopMetric = TopMetric.AMOUNT,
    current_user: User = Depends(get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> dict:
    """Get top N items by field.

    Returns top N items sorted by the specified metric.
    Supported for orders (field: platform) and order_items (field: product_name).

    Args:
        connection_id: Connection ID
        field: Field to group by
        date_from: Optional start date filter
        date_to: Optional end date filter
        limit: Number of items to return (1-50, default: 10)
        metric: Metric to sort by (count/amount/quantity)
        current_user: Authenticated user
        analytics_service: Analytics service instance

    Returns:
        Top N data with field, metric, and data points

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
        HTTPException: 400 if sheet type doesn't support top
        HTTPException: 400 if field not supported for this sheet type
        HTTPException: 400 if date_from > date_to
    """
    return await analytics_service.get_top(
        connection_id=connection_id,
        user_id=current_user.id,
        field=field,
        limit=limit,
        metric=metric,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/{connection_id}/data",
    response_model=DataResponse,
)
async def get_data(
    connection_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: SortOrder = SortOrder.DESC,
    current_user: User = Depends(get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> dict:
    """Get paginated data with search and filter.

    Returns paginated raw data with optional search, filter, and sort.
    Searchable fields vary by sheet type:
    - Orders: order_id, platform, order_status, customer_id
    - Order Items: order_item_id, order_id, product_id, product_name
    - Customers: customer_id, customer_name, phone
    - Products: product_id, product_name

    Args:
        connection_id: Connection ID
        page: Page number (1-indexed, default: 1)
        page_size: Number of records per page (1-100, default: 20)
        date_from: Optional start date filter (orders only)
        date_to: Optional end date filter (orders only)
        search: Optional search query
        sort_by: Optional field to sort by
        sort_order: Sort direction (asc/desc, default: desc)
        current_user: Authenticated user
        analytics_service: Analytics service instance

    Returns:
        Paginated data with total count and total pages

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
        HTTPException: 400 if sort_by field not supported
        HTTPException: 400 if date_from > date_to
    """
    return await analytics_service.get_data(
        connection_id=connection_id,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        date_from=date_from,
        date_to=date_to,
    )
