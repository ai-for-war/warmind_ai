"""Data query service for AI agent data operations.

Provides methods for querying user's sheet data with aggregations,
top items, and custom pipelines.
"""

from datetime import datetime
from typing import Any, Optional

from app.repo.sheet_connection_repo import SheetConnectionRepository
from app.repo.sheet_data_repo import SheetDataRepository
from app.services.ai.pipeline_validator import (
    PipelineValidator,
    PipelineValidationError,
)


class DataQueryService:
    """Service for querying user's sheet data.

    Provides methods for:
    - Getting user connections with schemas
    - Aggregation operations (sum, count, avg, min, max)
    - Top N queries
    - Custom aggregation pipelines

    Requirements: 4.1, 4.2, 5.1, 5.2, 6.1, 6.2, 8.1
    """

    VALID_OPERATIONS: set[str] = {"sum", "count", "avg", "min", "max"}

    def __init__(
        self,
        connection_repo: SheetConnectionRepository,
        data_repo: SheetDataRepository,
        pipeline_validator: PipelineValidator,
    ):
        """Initialize DataQueryService.

        Args:
            connection_repo: Repository for sheet connections
            data_repo: Repository for sheet raw data
            pipeline_validator: Validator for aggregation pipelines
        """
        self.connection_repo = connection_repo
        self.data_repo = data_repo
        self.pipeline_validator = pipeline_validator

    async def get_user_connections(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get all connections with schemas for a user.

        Returns connection info including field names, types, and sample values.

        Args:
            user_id: User ID to get connections for

        Returns:
            List of connection dicts with schema information
        """
        connections = await self.connection_repo.find_by_user_id(
            user_id,
            organization_id=organization_id,
        )

        result: list[dict[str, Any]] = []

        for conn in connections:
            # Get sample data to infer types
            sample_data, _ = await self.data_repo.find_by_connection_id(
                conn.id, page=1, page_size=5
            )

            # Build schema from column mappings and sample data
            fields: list[dict[str, Any]] = []
            sample_values: dict[str, Any] = {}

            if sample_data:
                # Get sample values from first row
                first_row = sample_data[0].data if sample_data else {}
                sample_values = first_row

            for mapping in conn.column_mappings:
                field_info: dict[str, Any] = {
                    "name": mapping.system_field,
                    "type": mapping.data_type,
                    "source_column": mapping.sheet_column,
                }

                # Add sample value if available
                if mapping.system_field in sample_values:
                    field_info["sample_value"] = sample_values[mapping.system_field]

                fields.append(field_info)

            result.append(
                {
                    "connection_id": conn.id,
                    "connection_name": conn.sheet_name,
                    "sheet_id": conn.sheet_id,
                    "fields": fields,
                    "sync_enabled": conn.sync_enabled,
                }
            )

        return result

    async def aggregate(
        self,
        connection_id: str,
        operation: str,
        field: Optional[str] = None,
        group_by: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
        date_field: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        user_connection_ids: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Execute aggregation query on sheet data.

        Args:
            connection_id: Connection ID to query
            operation: Aggregation operation (sum, count, avg, min, max)
            field: Field to aggregate (required for sum, avg, min, max)
            group_by: Optional field to group results by
            filters: Optional filter conditions
            date_field: Field name for date filtering
            date_from: Start date (ISO format string)
            date_to: End date (ISO format string)
            user_connection_ids: List of user's connection IDs for validation

        Returns:
            List of aggregation results

        Raises:
            PipelineValidationError: If operation is invalid or access denied
        """
        # Validate operation
        if operation not in self.VALID_OPERATIONS:
            raise PipelineValidationError(
                f"Invalid operation '{operation}'. "
                f"Valid operations: {', '.join(sorted(self.VALID_OPERATIONS))}"
            )

        # Validate field requirement
        if operation != "count" and not field:
            raise PipelineValidationError(
                f"Field is required for '{operation}' operation"
            )

        # Validate connection ownership
        if user_connection_ids:
            self.pipeline_validator.validate_connection_ownership(
                connection_id, user_connection_ids
            )

        # Build aggregation pipeline
        pipeline: list[dict[str, Any]] = []

        # Match stage - filter by connection_id
        match_stage: dict[str, Any] = {"connection_id": connection_id}

        # Add custom filters
        if filters:
            for key, value in filters.items():
                match_stage[f"data.{key}"] = value

        # Add date filters
        if date_field and (date_from or date_to):
            date_filter: dict[str, Any] = {}
            if date_from:
                date_filter["$gte"] = self._parse_date(date_from)
            if date_to:
                date_filter["$lte"] = self._parse_date(date_to)
            match_stage[f"data.{date_field}"] = date_filter

        pipeline.append({"$match": match_stage})

        # Group stage
        group_stage: dict[str, Any] = {}

        if group_by:
            group_stage["_id"] = f"$data.{group_by}"
        else:
            group_stage["_id"] = None

        # Add aggregation expression
        if operation == "count":
            group_stage["result"] = {"$sum": 1}
        elif operation == "sum":
            group_stage["result"] = {"$sum": f"$data.{field}"}
        elif operation == "avg":
            group_stage["result"] = {"$avg": f"$data.{field}"}
        elif operation == "min":
            group_stage["result"] = {"$min": f"$data.{field}"}
        elif operation == "max":
            group_stage["result"] = {"$max": f"$data.{field}"}

        pipeline.append({"$group": group_stage})

        # Sort by result descending if grouped
        if group_by:
            pipeline.append({"$sort": {"result": -1}})

        # Project to clean output
        project_stage: dict[str, Any] = {
            "_id": 0,
            "result": 1,
        }
        if group_by:
            project_stage[group_by] = "$_id"

        pipeline.append({"$project": project_stage})

        # Add limit
        pipeline.append({"$limit": self.pipeline_validator.MAX_LIMIT})

        # Execute pipeline
        return await self.data_repo.aggregate(pipeline)

    async def get_top_items(
        self,
        connection_id: str,
        sort_field: str,
        sort_order: str = "desc",
        limit: int = 10,
        group_by: Optional[str] = None,
        aggregate_field: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
        user_connection_ids: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Get top N items by a field.

        Args:
            connection_id: Connection ID to query
            sort_field: Field to sort by
            sort_order: Sort order ('asc' or 'desc')
            limit: Number of items to return (max 1000)
            group_by: Optional field to group by before sorting
            aggregate_field: Field to aggregate when grouping
            filters: Optional filter conditions
            user_connection_ids: List of user's connection IDs for validation

        Returns:
            List of top items

        Raises:
            PipelineValidationError: If access denied
        """
        # Validate connection ownership
        if user_connection_ids:
            self.pipeline_validator.validate_connection_ownership(
                connection_id, user_connection_ids
            )

        # Enforce max limit
        limit = min(limit, self.pipeline_validator.MAX_LIMIT)

        # Build pipeline
        pipeline: list[dict[str, Any]] = []

        # Match stage
        match_stage: dict[str, Any] = {"connection_id": connection_id}
        if filters:
            for key, value in filters.items():
                match_stage[f"data.{key}"] = value
        pipeline.append({"$match": match_stage})

        # If grouping, add group stage
        if group_by:
            group_stage: dict[str, Any] = {
                "_id": f"$data.{group_by}",
            }

            if aggregate_field:
                group_stage["total"] = {"$sum": f"$data.{aggregate_field}"}
            else:
                group_stage["count"] = {"$sum": 1}

            pipeline.append({"$group": group_stage})

            # Sort by aggregated value
            sort_value = -1 if sort_order == "desc" else 1
            sort_key = "total" if aggregate_field else "count"
            pipeline.append({"$sort": {sort_key: sort_value}})

            # Project
            project_stage: dict[str, Any] = {
                "_id": 0,
                group_by: "$_id",
            }
            if aggregate_field:
                project_stage["total"] = 1
            else:
                project_stage["count"] = 1
            pipeline.append({"$project": project_stage})
        else:
            # Sort directly by field
            sort_value = -1 if sort_order == "desc" else 1
            pipeline.append({"$sort": {f"data.{sort_field}": sort_value}})

            # Project data fields
            pipeline.append({"$project": {"_id": 0, "data": 1}})

        # Limit
        pipeline.append({"$limit": limit})

        # Execute pipeline
        return await self.data_repo.aggregate(pipeline)

    async def execute_pipeline(
        self,
        connection_id: str,
        pipeline: list[dict[str, Any]],
        user_connection_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Execute validated aggregation pipeline.

        Args:
            connection_id: Primary connection ID for the query
            pipeline: MongoDB aggregation pipeline stages
            user_connection_ids: List of connection IDs belonging to the user

        Returns:
            List of aggregation results

        Raises:
            PipelineValidationError: If pipeline is invalid or access denied
        """
        # Validate connection ownership
        self.pipeline_validator.validate_connection_ownership(
            connection_id, user_connection_ids
        )

        # Prepend connection_id filter to ensure data isolation
        connection_match = {"$match": {"connection_id": connection_id}}

        # Validate and sanitize the pipeline
        validated_pipeline = self.pipeline_validator.validate(
            pipeline, user_connection_ids
        )

        # Build final pipeline with connection filter first
        final_pipeline = [connection_match] + validated_pipeline

        # Execute pipeline
        return await self.data_repo.aggregate(final_pipeline)

    async def compare_periods(
        self,
        connection_id: str,
        operation: str,
        date_field: str,
        period1_from: str,
        period1_to: str,
        period2_from: str,
        period2_to: str,
        field: Optional[str] = None,
        group_by: Optional[str] = None,
        user_connection_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Compare metrics between two time periods.

        Args:
            connection_id: Connection ID to query
            operation: Aggregation operation (sum, count, avg)
            date_field: Field name for date filtering
            period1_from: Start date of period 1 (ISO format)
            period1_to: End date of period 1 (ISO format)
            period2_from: Start date of period 2 (ISO format)
            period2_to: End date of period 2 (ISO format)
            field: Field to aggregate (required for sum, avg)
            group_by: Optional field to group results by
            user_connection_ids: List of user's connection IDs for validation

        Returns:
            Dict with period1_value, period2_value, difference, percentage_change

        Raises:
            PipelineValidationError: If operation is invalid or access denied
        """
        # Validate operation (only sum, count, avg for comparison)
        valid_compare_ops = {"sum", "count", "avg"}
        if operation not in valid_compare_ops:
            raise PipelineValidationError(
                f"Invalid operation '{operation}' for comparison. "
                f"Valid operations: {', '.join(sorted(valid_compare_ops))}"
            )

        # Get period 1 result
        period1_results = await self.aggregate(
            connection_id=connection_id,
            operation=operation,
            field=field,
            group_by=group_by,
            date_field=date_field,
            date_from=period1_from,
            date_to=period1_to,
            user_connection_ids=user_connection_ids,
        )

        # Get period 2 result
        period2_results = await self.aggregate(
            connection_id=connection_id,
            operation=operation,
            field=field,
            group_by=group_by,
            date_field=date_field,
            date_from=period2_from,
            date_to=period2_to,
            user_connection_ids=user_connection_ids,
        )

        # Extract values
        period1_value = period1_results[0]["result"] if period1_results else 0
        period2_value = period2_results[0]["result"] if period2_results else 0

        # Calculate difference and percentage change
        difference = period2_value - period1_value

        if period1_value != 0:
            percentage_change = (difference / period1_value) * 100
        else:
            percentage_change = 100.0 if period2_value > 0 else 0.0

        return {
            "period1_value": period1_value,
            "period2_value": period2_value,
            "difference": difference,
            "percentage_change": round(percentage_change, 2),
            "period1": {"from": period1_from, "to": period1_to},
            "period2": {"from": period2_from, "to": period2_to},
        }

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime.

        Supports ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).

        Args:
            date_str: Date string in ISO format

        Returns:
            Parsed datetime object
        """
        try:
            # Try full ISO format first
            if "T" in date_str:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            # Try date-only format
            return datetime.fromisoformat(date_str)
        except ValueError:
            # Fallback to basic parsing
            return datetime.strptime(date_str, "%Y-%m-%d")
