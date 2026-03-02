"""Tools for the Data Agent.

Factory functions that create LangChain tools bound to user's connections.
Each tool is created with the user's connection context for data isolation.

Requirements: 4.1-4.4, 5.1-5.5, 6.1-6.4, 7.1-7.4, 8.1-8.4
"""

import json
from datetime import datetime, date
from typing import Any, Optional

from langchain_core.tools import tool

from app.common.service import get_data_query_service
from app.services.ai.pipeline_validator import PipelineValidationError


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def _json_dumps(data: Any, **kwargs) -> str:
    """JSON dumps with datetime support.

    Args:
        data: Data to serialize
        **kwargs: Additional arguments for json.dumps

    Returns:
        JSON string
    """
    return json.dumps(data, cls=DateTimeEncoder, **kwargs)


def _get_connection_id_by_name(
    user_connections: list[dict[str, Any]],
    connection_name: str,
) -> Optional[str]:
    """Get connection_id by connection name.

    Args:
        user_connections: List of user's connections
        connection_name: Name of the connection to find

    Returns:
        Connection ID if found, None otherwise
    """
    for conn in user_connections:
        if conn["connection_name"].lower() == connection_name.lower():
            return conn["connection_id"]
    return None


def _get_user_connection_ids(user_connections: list[dict[str, Any]]) -> list[str]:
    """Extract all connection IDs from user connections.

    Args:
        user_connections: List of user's connections

    Returns:
        List of connection IDs
    """
    return [conn["connection_id"] for conn in user_connections]


def create_get_data_schema_tool(user_connections: list[dict[str, Any]]):
    """Create get_data_schema tool bound to user's connections.

    Args:
        user_connections: List of user's sheet connections with schemas

    Returns:
        LangChain tool for getting data schema

    Requirements: 4.1, 4.2, 4.3, 4.4
    """

    @tool
    def get_data_schema(connection_name: Optional[str] = None) -> str:
        """Get schema of user's data connections.

        Lists available data sources and their fields. Use this to understand
        what data is available before querying.

        Args:
            connection_name: Optional name of specific connection to get details for.
                           If not provided, returns all connections.

        Returns:
            JSON string with connection names, field names, data types, and sample values.
        """
        if not user_connections:
            return json.dumps(
                {"error": "No data connections found. Please set up data sync first."}
            )

        if connection_name:
            # Find specific connection
            for conn in user_connections:
                if conn["connection_name"].lower() == connection_name.lower():
                    return json.dumps(
                        {
                            "connection_name": conn["connection_name"],
                            "connection_id": conn["connection_id"],
                            "fields": conn["fields"],
                            "sync_enabled": conn["sync_enabled"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )

            # Connection not found
            available = [c["connection_name"] for c in user_connections]
            return json.dumps(
                {
                    "error": f"Connection '{connection_name}' not found.",
                    "available_connections": available,
                },
                ensure_ascii=False,
            )

        # Return all connections summary
        result = []
        for conn in user_connections:
            result.append(
                {
                    "connection_name": conn["connection_name"],
                    "connection_id": conn["connection_id"],
                    "field_count": len(conn["fields"]),
                    "fields": [f["name"] for f in conn["fields"]],
                    "sync_enabled": conn["sync_enabled"],
                }
            )

        return json.dumps(result, ensure_ascii=False, indent=2)

    return get_data_schema


def create_aggregate_data_tool(user_connections: list[dict[str, Any]]):
    """Create aggregate_data tool bound to user's connections.

    Args:
        user_connections: List of user's sheet connections with schemas

    Returns:
        LangChain tool for aggregating data

    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
    """
    user_connection_ids = _get_user_connection_ids(user_connections)

    @tool
    async def aggregate_data(
        connection_name: str,
        operation: str,
        field: Optional[str] = None,
        group_by: Optional[str] = None,
        filters: Optional[str] = None,
        date_field: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> str:
        """Perform aggregation on data (sum, count, avg, min, max).

        Use this for simple aggregations like totals, counts, and averages.

        Args:
            connection_name: Name of the data connection to query
            operation: Aggregation operation - one of: sum, count, avg, min, max
            field: Field to aggregate (required for sum, avg, min, max)
            group_by: Optional field to group results by
            filters: Optional JSON string of filter conditions (e.g., '{"status": "completed"}')
            date_field: Field name for date filtering
            date_from: Start date in ISO format (YYYY-MM-DD)
            date_to: End date in ISO format (YYYY-MM-DD)

        Returns:
            JSON string with aggregation results
        """
        # Get connection_id
        connection_id = _get_connection_id_by_name(user_connections, connection_name)
        if not connection_id:
            available = [c["connection_name"] for c in user_connections]
            return json.dumps(
                {
                    "error": f"Connection '{connection_name}' not found.",
                    "available_connections": available,
                },
                ensure_ascii=False,
            )

        # Parse filters if provided
        parsed_filters = None
        if filters:
            try:
                parsed_filters = json.loads(filters)
            except json.JSONDecodeError:
                return json.dumps(
                    {"error": "Invalid filters format. Must be valid JSON."}
                )

        try:
            data_query_service = get_data_query_service()
            results = await data_query_service.aggregate(
                connection_id=connection_id,
                operation=operation,
                field=field,
                group_by=group_by,
                filters=parsed_filters,
                date_field=date_field,
                date_from=date_from,
                date_to=date_to,
                user_connection_ids=user_connection_ids,
            )

            return _json_dumps(
                {
                    "connection_name": connection_name,
                    "operation": operation,
                    "field": field,
                    "group_by": group_by,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )

        except PipelineValidationError as e:
            return _json_dumps({"error": str(e)}, ensure_ascii=False)
        except Exception as e:
            return _json_dumps({"error": f"Query failed: {str(e)}"}, ensure_ascii=False)

    return aggregate_data


def create_get_top_items_tool(user_connections: list[dict[str, Any]]):
    """Create get_top_items tool bound to user's connections.

    Args:
        user_connections: List of user's sheet connections with schemas

    Returns:
        LangChain tool for getting top items

    Requirements: 6.1, 6.2, 6.3, 6.4
    """
    user_connection_ids = _get_user_connection_ids(user_connections)

    @tool
    async def get_top_items(
        connection_name: str,
        sort_field: str,
        sort_order: str = "desc",
        limit: int = 10,
        group_by: Optional[str] = None,
        aggregate_field: Optional[str] = None,
        filters: Optional[str] = None,
    ) -> str:
        """Get top N items by a field.

        Use this to find best performers, highest values, or rankings.

        Args:
            connection_name: Name of the data connection to query
            sort_field: Field to sort by
            sort_order: Sort order - 'desc' for highest first, 'asc' for lowest first
            limit: Number of items to return (default 10, max 1000)
            group_by: Optional field to group by before sorting
            aggregate_field: Field to sum when grouping (e.g., revenue per product)
            filters: Optional JSON string of filter conditions

        Returns:
            JSON string with top items
        """
        # Get connection_id
        connection_id = _get_connection_id_by_name(user_connections, connection_name)
        if not connection_id:
            available = [c["connection_name"] for c in user_connections]
            return json.dumps(
                {
                    "error": f"Connection '{connection_name}' not found.",
                    "available_connections": available,
                },
                ensure_ascii=False,
            )

        # Parse filters if provided
        parsed_filters = None
        if filters:
            try:
                parsed_filters = json.loads(filters)
            except json.JSONDecodeError:
                return json.dumps(
                    {"error": "Invalid filters format. Must be valid JSON."}
                )

        # Validate sort_order
        if sort_order not in ("asc", "desc"):
            return json.dumps({"error": "sort_order must be 'asc' or 'desc'"})

        try:
            data_query_service = get_data_query_service()
            results = await data_query_service.get_top_items(
                connection_id=connection_id,
                sort_field=sort_field,
                sort_order=sort_order,
                limit=limit,
                group_by=group_by,
                aggregate_field=aggregate_field,
                filters=parsed_filters,
                user_connection_ids=user_connection_ids,
            )

            return _json_dumps(
                {
                    "connection_name": connection_name,
                    "sort_field": sort_field,
                    "sort_order": sort_order,
                    "limit": limit,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )

        except PipelineValidationError as e:
            return _json_dumps({"error": str(e)}, ensure_ascii=False)
        except Exception as e:
            return _json_dumps({"error": f"Query failed: {str(e)}"}, ensure_ascii=False)

    return get_top_items


def create_compare_periods_tool(user_connections: list[dict[str, Any]]):
    """Create compare_periods tool bound to user's connections.

    Args:
        user_connections: List of user's sheet connections with schemas

    Returns:
        LangChain tool for comparing time periods

    Requirements: 7.1, 7.2, 7.3, 7.4
    """
    user_connection_ids = _get_user_connection_ids(user_connections)

    @tool
    async def compare_periods(
        connection_name: str,
        operation: str,
        date_field: str,
        period1_from: str,
        period1_to: str,
        period2_from: str,
        period2_to: str,
        field: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> str:
        """Compare metrics between two time periods.

        Use this to track trends, compare week-over-week, month-over-month, etc.

        Args:
            connection_name: Name of the data connection to query
            operation: Aggregation operation - one of: sum, count, avg
            date_field: Field name containing dates for filtering
            period1_from: Start date of period 1 (YYYY-MM-DD)
            period1_to: End date of period 1 (YYYY-MM-DD)
            period2_from: Start date of period 2 (YYYY-MM-DD)
            period2_to: End date of period 2 (YYYY-MM-DD)
            field: Field to aggregate (required for sum, avg)
            group_by: Optional field to group results by

        Returns:
            JSON string with period1_value, period2_value, difference, percentage_change
        """
        # Get connection_id
        connection_id = _get_connection_id_by_name(user_connections, connection_name)
        if not connection_id:
            available = [c["connection_name"] for c in user_connections]
            return json.dumps(
                {
                    "error": f"Connection '{connection_name}' not found.",
                    "available_connections": available,
                },
                ensure_ascii=False,
            )

        # Validate operation
        valid_ops = {"sum", "count", "avg"}
        if operation not in valid_ops:
            return json.dumps(
                {
                    "error": f"Invalid operation '{operation}'. Valid: {', '.join(valid_ops)}"
                }
            )

        try:
            data_query_service = get_data_query_service()
            result = await data_query_service.compare_periods(
                connection_id=connection_id,
                operation=operation,
                date_field=date_field,
                period1_from=period1_from,
                period1_to=period1_to,
                period2_from=period2_from,
                period2_to=period2_to,
                field=field,
                group_by=group_by,
                user_connection_ids=user_connection_ids,
            )

            return _json_dumps(
                {
                    "connection_name": connection_name,
                    "operation": operation,
                    "field": field,
                    **result,
                },
                ensure_ascii=False,
                indent=2,
            )

        except PipelineValidationError as e:
            return _json_dumps({"error": str(e)}, ensure_ascii=False)
        except Exception as e:
            return _json_dumps({"error": f"Query failed: {str(e)}"}, ensure_ascii=False)

    return compare_periods


def create_execute_aggregation_tool(user_connections: list[dict[str, Any]]):
    """Create execute_aggregation tool bound to user's connections.

    Args:
        user_connections: List of user's sheet connections with schemas

    Returns:
        LangChain tool for executing custom aggregation pipelines

    Requirements: 8.1, 8.2, 8.3, 8.4
    """
    user_connection_ids = _get_user_connection_ids(user_connections)

    @tool
    async def execute_aggregation(
        connection_name: str,
        pipeline: str,
        description: str,
    ) -> str:
        """Execute custom MongoDB aggregation pipeline.

        Use this for complex queries that simple tools can't handle,
        such as joins ($lookup) between multiple data sources.

        IMPORTANT: The pipeline will be validated for security.
        Allowed stages: $match, $group, $sort, $limit, $project, $lookup, $unwind, $count
        Blocked stages: $out, $merge, $delete

        Args:
            connection_name: Name of the primary data connection
            pipeline: JSON string of MongoDB aggregation pipeline stages
            description: Brief description of what this query does

        Returns:
            JSON string with query results (max 1000 rows)
        """
        # Get connection_id
        connection_id = _get_connection_id_by_name(user_connections, connection_name)
        if not connection_id:
            available = [c["connection_name"] for c in user_connections]
            return json.dumps(
                {
                    "error": f"Connection '{connection_name}' not found.",
                    "available_connections": available,
                },
                ensure_ascii=False,
            )

        # Parse pipeline
        try:
            parsed_pipeline = json.loads(pipeline)
            if not isinstance(parsed_pipeline, list):
                return json.dumps({"error": "Pipeline must be a JSON array of stages."})
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid pipeline JSON: {str(e)}"})

        try:
            data_query_service = get_data_query_service()
            results = await data_query_service.execute_pipeline(
                connection_id=connection_id,
                pipeline=parsed_pipeline,
                user_connection_ids=user_connection_ids,
            )

            return _json_dumps(
                {
                    "connection_name": connection_name,
                    "description": description,
                    "result_count": len(results),
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )

        except PipelineValidationError as e:
            return _json_dumps(
                {"error": f"Pipeline validation failed: {str(e)}"}, ensure_ascii=False
            )
        except Exception as e:
            return _json_dumps(
                {"error": f"Query execution failed: {str(e)}"}, ensure_ascii=False
            )

    return execute_aggregation
