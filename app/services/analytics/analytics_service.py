"""Analytics service for computing and caching analytics data."""

import logging
import math
from datetime import date
from typing import Any, Optional

from fastapi import HTTPException, status

from app.domain.schemas.analytics import (
    Granularity,
    SheetType,
    SortOrder,
    TimeSeriesMetrics,
    TopMetric,
)
from app.repo.sheet_connection_repo import SheetConnectionRepository
from app.repo.sheet_data_repo import SheetDataRepository
from app.services.analytics.cache_manager import AnalyticsCacheManager
from app.services.analytics.sheet_type_detector import detect_sheet_type
from app.services.analytics.strategies import (
    BaseAnalyticsStrategy,
    CustomersAnalyticsStrategy,
    OrderItemsAnalyticsStrategy,
    OrdersAnalyticsStrategy,
    ProductsAnalyticsStrategy,
)

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for computing analytics from synced sheet data."""

    def __init__(
        self,
        connection_repo: SheetConnectionRepository,
        data_repo: SheetDataRepository,
        cache_manager: AnalyticsCacheManager,
    ):
        """
        Initialize analytics service.

        Args:
            connection_repo: Repository for sheet connections.
            data_repo: Repository for sheet raw data.
            cache_manager: Cache manager for analytics results.
        """
        self.connection_repo = connection_repo
        self.data_repo = data_repo
        self.cache_manager = cache_manager
        self.strategies: dict[SheetType, BaseAnalyticsStrategy] = {
            SheetType.ORDERS: OrdersAnalyticsStrategy(),
            SheetType.ORDER_ITEMS: OrderItemsAnalyticsStrategy(),
            SheetType.CUSTOMERS: CustomersAnalyticsStrategy(),
            SheetType.PRODUCTS: ProductsAnalyticsStrategy(),
        }

    async def _get_connection_and_strategy(
        self,
        connection_id: str,
        user_id: str,
    ) -> tuple[Any, BaseAnalyticsStrategy, SheetType]:
        """
        Get connection and appropriate strategy.

        Args:
            connection_id: The connection ID.
            user_id: The user ID for access control.

        Returns:
            Tuple of (connection, strategy, sheet_type).

        Raises:
            HTTPException: If connection not found or access denied.
        """
        connection = await self.connection_repo.find_by_id(connection_id)

        if connection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found",
            )

        if connection.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found",
            )

        sheet_type = detect_sheet_type(connection.sheet_name)
        strategy = self.strategies[sheet_type]

        return connection, strategy, sheet_type

    def _validate_date_range(
        self,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> None:
        """
        Validate date range parameters.

        Args:
            date_from: Start date.
            date_to: End date.

        Raises:
            HTTPException: If date_from > date_to.
        """
        if date_from and date_to and date_from > date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date range: date_from must be before date_to",
            )

    async def get_summary(
        self,
        connection_id: str,
        user_id: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> dict:
        """
        Get summary metrics for a connection.

        Args:
            connection_id: The connection ID.
            user_id: The user ID for access control.
            date_from: Optional start date filter.
            date_to: Optional end date filter.

        Returns:
            Summary metrics dict.
        """
        self._validate_date_range(date_from, date_to)
        _, strategy, sheet_type = await self._get_connection_and_strategy(
            connection_id, user_id
        )

        # Build cache params
        params = {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        }

        # Check cache
        cached = await self.cache_manager.get(connection_id, "summary", params)
        if cached is not None:
            return cached

        # Compute summary
        pipeline = strategy.get_summary_pipeline(connection_id, date_from, date_to)
        results = await self.data_repo.aggregate(pipeline)

        # Format response based on sheet type
        if not results:
            if sheet_type == SheetType.ORDERS:
                data = {"total_count": 0, "total_amount": 0.0, "avg_amount": 0.0}
            elif sheet_type == SheetType.ORDER_ITEMS:
                data = {
                    "total_quantity": 0,
                    "total_line_total": 0.0,
                    "unique_products": 0,
                }
            else:
                data = {"total_count": 0}
        else:
            result = results[0]
            if sheet_type == SheetType.ORDERS:
                data = {
                    "total_count": result.get("total_count", 0),
                    "total_amount": result.get("total_amount", 0.0) or 0.0,
                    "avg_amount": result.get("avg_amount", 0.0) or 0.0,
                }
            elif sheet_type == SheetType.ORDER_ITEMS:
                data = {
                    "total_quantity": int(result.get("total_quantity", 0) or 0),
                    "total_line_total": result.get("total_line_total", 0.0) or 0.0,
                    "unique_products": result.get("unique_products", 0),
                }
            else:
                data = {"total_count": result.get("total_count", 0)}

        # Cache and return
        await self.cache_manager.set(connection_id, "summary", params, data)
        return data

    async def get_time_series(
        self,
        connection_id: str,
        user_id: str,
        date_from: date,
        date_to: date,
        granularity: Granularity = Granularity.DAY,
        metrics: TimeSeriesMetrics = TimeSeriesMetrics.BOTH,
    ) -> dict:
        """
        Get time series data for a connection.

        Args:
            connection_id: The connection ID.
            user_id: The user ID for access control.
            date_from: Start date (required).
            date_to: End date (required).
            granularity: Time grouping granularity.
            metrics: Which metrics to include.

        Returns:
            Time series data dict.

        Raises:
            HTTPException: If sheet type doesn't support time series.
        """
        self._validate_date_range(date_from, date_to)
        _, strategy, sheet_type = await self._get_connection_and_strategy(
            connection_id, user_id
        )

        if not strategy.supports_time_series():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Time series not supported for sheet type '{sheet_type.value}'",
            )

        # Build cache params
        params = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "granularity": granularity.value,
            "metrics": metrics.value,
        }

        # Check cache
        cached = await self.cache_manager.get(connection_id, "time-series", params)
        if cached is not None:
            return cached

        # Compute time series (only OrdersAnalyticsStrategy has this method)
        if isinstance(strategy, OrdersAnalyticsStrategy):
            pipeline = strategy.get_time_series_pipeline(
                connection_id, date_from, date_to, granularity.value, metrics.value
            )
            results = await self.data_repo.aggregate(pipeline)

            data = {
                "granularity": granularity.value,
                "data": results,
            }

            # Cache and return
            await self.cache_manager.set(connection_id, "time-series", params, data)
            return data

        return {"granularity": granularity.value, "data": []}

    async def get_distribution(
        self,
        connection_id: str,
        user_id: str,
        field: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> dict:
        """
        Get distribution data for a field.

        Args:
            connection_id: The connection ID.
            user_id: The user ID for access control.
            field: Field to get distribution for.
            date_from: Optional start date filter.
            date_to: Optional end date filter.

        Returns:
            Distribution data dict.

        Raises:
            HTTPException: If sheet type doesn't support distribution or field not supported.
        """
        self._validate_date_range(date_from, date_to)
        _, strategy, sheet_type = await self._get_connection_and_strategy(
            connection_id, user_id
        )

        if not strategy.supports_distribution():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Distribution not supported for sheet type '{sheet_type.value}'",
            )

        if field not in strategy.get_distribution_fields():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field '{field}' not supported for this sheet type",
            )

        # Build cache params
        params = {
            "field": field,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        }

        # Check cache
        cached = await self.cache_manager.get(connection_id, "distribution", params)
        if cached is not None:
            return cached

        # Compute distribution (only OrdersAnalyticsStrategy has this method)
        if isinstance(strategy, OrdersAnalyticsStrategy):
            pipeline = strategy.get_distribution_pipeline(
                connection_id, field, date_from, date_to
            )
            results = await self.data_repo.aggregate(pipeline)

            data = {
                "field": field,
                "data": results,
            }

            # Cache and return
            await self.cache_manager.set(connection_id, "distribution", params, data)
            return data

        return {"field": field, "data": []}

    async def get_top(
        self,
        connection_id: str,
        user_id: str,
        field: str,
        limit: int = 10,
        metric: TopMetric = TopMetric.AMOUNT,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> dict:
        """
        Get top N items by field.

        Args:
            connection_id: The connection ID.
            user_id: The user ID for access control.
            field: Field to group by.
            limit: Number of items to return (1-50).
            metric: Metric to sort by.
            date_from: Optional start date filter.
            date_to: Optional end date filter.

        Returns:
            Top N data dict.

        Raises:
            HTTPException: If sheet type doesn't support top or field not supported.
        """
        self._validate_date_range(date_from, date_to)
        _, strategy, sheet_type = await self._get_connection_and_strategy(
            connection_id, user_id
        )

        if not strategy.supports_top():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Top not supported for sheet type '{sheet_type.value}'",
            )

        if field not in strategy.get_top_fields():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field '{field}' not supported for this sheet type",
            )

        # Build cache params
        params = {
            "field": field,
            "limit": limit,
            "metric": metric.value,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        }

        # Check cache
        cached = await self.cache_manager.get(connection_id, "top", params)
        if cached is not None:
            return cached

        # Compute top N
        if isinstance(strategy, (OrdersAnalyticsStrategy, OrderItemsAnalyticsStrategy)):
            pipeline = strategy.get_top_pipeline(
                connection_id, field, limit, metric.value, date_from, date_to
            )
            results = await self.data_repo.aggregate(pipeline)

            data = {
                "field": field,
                "metric": metric.value,
                "data": results,
            }

            # Cache and return
            await self.cache_manager.set(connection_id, "top", params, data)
            return data

        return {"field": field, "metric": metric.value, "data": []}

    async def get_data(
        self,
        connection_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: SortOrder = SortOrder.DESC,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> dict:
        """
        Get paginated data with search and filter.

        Args:
            connection_id: The connection ID.
            user_id: The user ID for access control.
            page: Page number (1-indexed).
            page_size: Number of items per page.
            search: Optional search query.
            sort_by: Optional field to sort by.
            sort_order: Sort direction.
            date_from: Optional start date filter.
            date_to: Optional end date filter.

        Returns:
            Paginated data dict.
        """
        self._validate_date_range(date_from, date_to)
        _, strategy, _ = await self._get_connection_and_strategy(connection_id, user_id)

        # Validate sort_by field
        if sort_by and sort_by not in strategy.get_sortable_fields():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field '{sort_by}' not supported for sorting",
            )

        # Calculate skip
        skip = (page - 1) * page_size

        # Get sort order as int
        sort_order_int = 1 if sort_order == SortOrder.ASC else -1

        # Get date field for filtering
        date_field = strategy.get_date_field()

        # Query data
        results, total = await self.data_repo.find_with_search(
            connection_id=connection_id,
            search=search,
            search_fields=strategy.get_searchable_fields(),
            date_field=date_field,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_order=sort_order_int,
            skip=skip,
            limit=page_size,
        )

        # Calculate total pages
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return {
            "data": results,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
