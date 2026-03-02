"""Analytics strategies for different sheet types."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional

from app.domain.schemas.analytics import SheetType


class BaseAnalyticsStrategy(ABC):
    """Base class for sheet type specific analytics."""

    @property
    @abstractmethod
    def sheet_type(self) -> SheetType:
        """Return the sheet type this strategy handles."""
        pass

    @abstractmethod
    def get_summary_pipeline(
        self,
        connection_id: str,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> list[dict]:
        """Return MongoDB aggregation pipeline for summary."""
        pass

    @abstractmethod
    def get_searchable_fields(self) -> list[str]:
        """Return list of fields that can be searched."""
        pass

    @abstractmethod
    def get_sortable_fields(self) -> list[str]:
        """Return list of fields that can be sorted."""
        pass

    def supports_time_series(self) -> bool:
        """Return whether this sheet type supports time series."""
        return False

    def supports_distribution(self) -> bool:
        """Return whether this sheet type supports distribution."""
        return False

    def get_distribution_fields(self) -> list[str]:
        """Return list of fields that can be used for distribution."""
        return []

    def supports_top(self) -> bool:
        """Return whether this sheet type supports top N queries."""
        return False

    def get_top_fields(self) -> list[str]:
        """Return list of fields that can be used for top N queries."""
        return []

    def get_date_field(self) -> Optional[str]:
        """Return the date field for this sheet type, if any."""
        return None


class OrdersAnalyticsStrategy(BaseAnalyticsStrategy):
    """Analytics strategy for orders sheet."""

    @property
    def sheet_type(self) -> SheetType:
        return SheetType.ORDERS

    def get_summary_pipeline(
        self,
        connection_id: str,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> list[dict]:
        """Return aggregation pipeline for orders summary."""
        match_stage: dict = {"connection_id": connection_id}

        if date_from or date_to:
            date_query: dict = {}
            if date_from:
                date_query["$gte"] = datetime.combine(date_from, datetime.min.time())
            if date_to:
                date_query["$lte"] = datetime.combine(date_to, datetime.max.time())
            match_stage["data.order_date"] = date_query

        return [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": None,
                    "total_count": {"$sum": 1},
                    "total_amount": {"$sum": {"$toDouble": "$data.total_amount"}},
                    "avg_amount": {"$avg": {"$toDouble": "$data.total_amount"}},
                }
            },
        ]

    def get_searchable_fields(self) -> list[str]:
        return ["order_id", "platform", "order_status", "customer_id"]

    def get_sortable_fields(self) -> list[str]:
        return [
            "order_id",
            "platform",
            "order_status",
            "order_date",
            "subtotal",
            "total_amount",
        ]

    def supports_time_series(self) -> bool:
        return True

    def supports_distribution(self) -> bool:
        return True

    def get_distribution_fields(self) -> list[str]:
        return ["platform", "order_status"]

    def supports_top(self) -> bool:
        return True

    def get_top_fields(self) -> list[str]:
        return ["platform"]

    def get_date_field(self) -> Optional[str]:
        return "order_date"

    def get_time_series_pipeline(
        self,
        connection_id: str,
        date_from: date,
        date_to: date,
        granularity: str,
        metrics: str,
    ) -> list[dict]:

        # Date format based on granularity
        date_formats = {
            "day": "%Y-%m-%d",
            "week": "%Y-W%V",
            "month": "%Y-%m",
            "year": "%Y",
        }
        date_format = date_formats.get(granularity, "%Y-%m-%d")

        # Convert date to datetime for MongoDB comparison
        date_from_dt = datetime.combine(date_from, datetime.min.time())
        date_to_dt = datetime.combine(date_to, datetime.max.time())

        match_stage = {
            "connection_id": connection_id,
            "data.order_date": {
                "$gte": date_from_dt,
                "$lte": date_to_dt,
            },
        }

        # Build group stage based on metrics
        group_stage: dict = {
            "_id": {
                "$dateToString": {
                    "format": date_format,
                    "date": "$data.order_date",
                }
            },
        }

        if metrics in ("count", "both"):
            group_stage["count"] = {"$sum": 1}
        if metrics in ("amount", "both"):
            group_stage["total_amount"] = {"$sum": {"$toDouble": "$data.total_amount"}}

        return [
            {"$match": match_stage},
            {"$group": group_stage},
            {"$sort": {"_id": 1}},
            {"$project": {"_id": 0, "date": "$_id", "count": 1, "total_amount": 1}},
        ]

    def get_distribution_pipeline(
        self,
        connection_id: str,
        field: str,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> list[dict]:
        """Return aggregation pipeline for distribution data."""
        match_stage: dict = {"connection_id": connection_id}

        if date_from or date_to:
            date_query: dict = {}
            if date_from:
                date_query["$gte"] = datetime.combine(date_from, datetime.min.time())
            if date_to:
                date_query["$lte"] = datetime.combine(date_to, datetime.max.time())
            match_stage["data.order_date"] = date_query

        return [
            {"$match": match_stage},
            {"$group": {"_id": f"$data.{field}", "count": {"$sum": 1}}},
            {
                "$group": {
                    "_id": None,
                    "items": {"$push": {"value": "$_id", "count": "$count"}},
                    "total": {"$sum": "$count"},
                }
            },
            {"$unwind": "$items"},
            {
                "$project": {
                    "_id": 0,
                    "value": "$items.value",
                    "count": "$items.count",
                    "percentage": {
                        "$round": [
                            {
                                "$multiply": [
                                    {"$divide": ["$items.count", "$total"]},
                                    100,
                                ]
                            },
                            1,
                        ]
                    },
                }
            },
            {"$sort": {"count": -1}},
        ]

    def get_top_pipeline(
        self,
        connection_id: str,
        field: str,
        limit: int,
        metric: str,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> list[dict]:
        """Return aggregation pipeline for top N data."""
        match_stage: dict = {"connection_id": connection_id}

        if date_from or date_to:
            date_query: dict = {}
            if date_from:
                date_query["$gte"] = datetime.combine(date_from, datetime.min.time())
            if date_to:
                date_query["$lte"] = datetime.combine(date_to, datetime.max.time())
            match_stage["data.order_date"] = date_query

        # Build group stage
        group_stage: dict = {
            "_id": f"$data.{field}",
            "count": {"$sum": 1},
            "total_amount": {"$sum": {"$toDouble": "$data.total_amount"}},
        }

        # Sort field based on metric
        sort_field = "total_amount" if metric == "amount" else "count"

        return [
            {"$match": match_stage},
            {"$group": group_stage},
            {"$sort": {sort_field: -1}},
            {"$limit": limit},
            {"$project": {"_id": 0, "value": "$_id", "count": 1, "total_amount": 1}},
        ]


class OrderItemsAnalyticsStrategy(BaseAnalyticsStrategy):
    """Analytics strategy for order_items sheet."""

    @property
    def sheet_type(self) -> SheetType:
        return SheetType.ORDER_ITEMS

    def get_summary_pipeline(
        self,
        connection_id: str,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> list[dict]:
        """Return aggregation pipeline for order items summary."""
        # Order items don't have date filtering
        return [
            {"$match": {"connection_id": connection_id}},
            {
                "$group": {
                    "_id": None,
                    "total_quantity": {"$sum": {"$toDouble": "$data.quantity"}},
                    "total_line_total": {"$sum": {"$toDouble": "$data.line_total"}},
                    "unique_products": {"$addToSet": "$data.product_id"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "total_quantity": 1,
                    "total_line_total": 1,
                    "unique_products": {"$size": "$unique_products"},
                }
            },
        ]

    def get_searchable_fields(self) -> list[str]:
        return ["order_item_id", "order_id", "product_id", "product_name"]

    def get_sortable_fields(self) -> list[str]:
        return [
            "order_item_id",
            "order_id",
            "product_id",
            "product_name",
            "quantity",
            "unit_price",
            "final_price",
            "line_total",
        ]

    def supports_top(self) -> bool:
        return True

    def get_top_fields(self) -> list[str]:
        return ["product_name"]

    def get_top_pipeline(
        self,
        connection_id: str,
        field: str,
        limit: int,
        metric: str,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> list[dict]:
        """Return aggregation pipeline for top N data."""
        # Build group stage
        group_stage: dict = {
            "_id": f"$data.{field}",
            "count": {"$sum": 1},
            "total_quantity": {"$sum": {"$toDouble": "$data.quantity"}},
        }

        # Sort field based on metric
        sort_field = "total_quantity" if metric == "quantity" else "count"

        return [
            {"$match": {"connection_id": connection_id}},
            {"$group": group_stage},
            {"$sort": {sort_field: -1}},
            {"$limit": limit},
            {"$project": {"_id": 0, "value": "$_id", "count": 1, "total_quantity": 1}},
        ]


class CustomersAnalyticsStrategy(BaseAnalyticsStrategy):
    """Analytics strategy for customers sheet."""

    @property
    def sheet_type(self) -> SheetType:
        return SheetType.CUSTOMERS

    def get_summary_pipeline(
        self,
        connection_id: str,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> list[dict]:
        """Return aggregation pipeline for customers summary."""
        return [
            {"$match": {"connection_id": connection_id}},
            {"$count": "total_count"},
        ]

    def get_searchable_fields(self) -> list[str]:
        return ["customer_id", "customer_name", "phone"]

    def get_sortable_fields(self) -> list[str]:
        return ["customer_id", "customer_name", "phone"]


class ProductsAnalyticsStrategy(BaseAnalyticsStrategy):
    """Analytics strategy for products sheet."""

    @property
    def sheet_type(self) -> SheetType:
        return SheetType.PRODUCTS

    def get_summary_pipeline(
        self,
        connection_id: str,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> list[dict]:
        """Return aggregation pipeline for products summary."""
        return [
            {"$match": {"connection_id": connection_id}},
            {"$count": "total_count"},
        ]

    def get_searchable_fields(self) -> list[str]:
        return ["product_id", "product_name"]

    def get_sortable_fields(self) -> list[str]:
        return ["product_id", "product_name"]
