"""API schemas for Sheet Analytics feature."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class SheetType(str, Enum):
    """Type of sheet being synced."""

    ORDERS = "orders"
    ORDER_ITEMS = "order_items"
    CUSTOMERS = "customers"
    PRODUCTS = "products"


class Granularity(str, Enum):
    """Time series granularity options."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class TimeSeriesMetrics(str, Enum):
    """Metrics to include in time series response."""

    COUNT = "count"
    AMOUNT = "amount"
    BOTH = "both"


class TopMetric(str, Enum):
    """Metric to sort top N results by."""

    COUNT = "count"
    AMOUNT = "amount"
    QUANTITY = "quantity"


class SortOrder(str, Enum):
    """Sort order for data queries."""

    ASC = "asc"
    DESC = "desc"


# Summary Response Schemas - varies by sheet type
class OrdersSummaryResponse(BaseModel):
    """Summary response for orders sheet type."""

    total_count: int
    total_amount: float
    avg_amount: float


class OrderItemsSummaryResponse(BaseModel):
    """Summary response for order_items sheet type."""

    total_quantity: int
    total_line_total: float
    unique_products: int


class SimpleSummaryResponse(BaseModel):
    """Summary response for customers and products sheet types."""

    total_count: int


# Time Series Response Schemas
class TimeSeriesDataPoint(BaseModel):
    """Single data point in time series response."""

    date: str
    count: Optional[int] = None
    total_amount: Optional[float] = None


class TimeSeriesResponse(BaseModel):
    """Response for time series analytics endpoint."""

    granularity: Granularity
    data: list[TimeSeriesDataPoint]


# Distribution Response Schemas
class DistributionDataPoint(BaseModel):
    """Single data point in distribution response."""

    value: str
    count: int
    percentage: float


class DistributionResponse(BaseModel):
    """Response for distribution analytics endpoint."""

    field: str
    data: list[DistributionDataPoint]


# Top N Response Schemas
class TopDataPoint(BaseModel):
    """Single data point in top N response."""

    value: str
    count: int
    total_amount: Optional[float] = None
    total_quantity: Optional[int] = None


class TopResponse(BaseModel):
    """Response for top N analytics endpoint."""

    field: str
    metric: str
    data: list[TopDataPoint]


# Data Response Schema
class DataResponse(BaseModel):
    """Response for paginated data endpoint with search/filter."""

    data: list[dict]
    total: int
    page: int
    page_size: int
    total_pages: int
