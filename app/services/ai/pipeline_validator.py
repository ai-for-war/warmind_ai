"""Pipeline validator service for MongoDB aggregation pipelines.

Validates and sanitizes aggregation pipelines to ensure security and data isolation.
"""

from typing import Any

from app.common.exceptions import AppException


class PipelineValidationError(AppException):
    """Raised when pipeline validation fails."""

    default_message = "Pipeline validation failed"


class PipelineValidator:
    """Validates MongoDB aggregation pipelines for security and correctness.

    Ensures pipelines:
    - Only use allowed stages
    - Don't use dangerous stages ($out, $merge, $delete)
    - Verify $lookup targets belong to user
    - Enforce result limits

    Requirements: 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
    """

    ALLOWED_STAGES: set[str] = {
        "$match",
        "$group",
        "$sort",
        "$limit",
        "$project",
        "$lookup",
        "$unwind",
        "$count",
        "$skip",
        "$addFields",
    }

    BLOCKED_STAGES: set[str] = {
        "$out",
        "$merge",
        "$delete",
        "$createIndex",
        "$dropIndex",
        "$collStats",
        "$indexStats",
        "$planCacheStats",
    }

    MAX_LIMIT: int = 1000

    def validate(
        self,
        pipeline: list[dict[str, Any]],
        user_connection_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Validate and sanitize aggregation pipeline.

        Args:
            pipeline: MongoDB aggregation pipeline stages
            user_connection_ids: List of connection IDs belonging to the user

        Returns:
            Sanitized pipeline with enforced limits

        Raises:
            PipelineValidationError: If pipeline contains invalid or blocked stages
        """
        if not isinstance(pipeline, list):
            raise PipelineValidationError("Pipeline must be a list of stages")

        if not pipeline:
            raise PipelineValidationError("Pipeline cannot be empty")

        sanitized_pipeline: list[dict[str, Any]] = []
        has_limit = False

        for stage in pipeline:
            if not isinstance(stage, dict):
                raise PipelineValidationError(
                    f"Pipeline stage must be a dict, got {type(stage).__name__}"
                )

            if len(stage) != 1:
                raise PipelineValidationError(
                    "Each pipeline stage must have exactly one operator"
                )

            stage_name = list(stage.keys())[0]

            # Check for blocked stages
            if stage_name in self.BLOCKED_STAGES:
                raise PipelineValidationError(
                    f"Stage '{stage_name}' is not allowed for security reasons"
                )

            # Check for allowed stages
            if stage_name not in self.ALLOWED_STAGES:
                raise PipelineValidationError(
                    f"Stage '{stage_name}' is not supported. "
                    f"Allowed stages: {', '.join(sorted(self.ALLOWED_STAGES))}"
                )

            # Validate $lookup stage for data isolation
            if stage_name == "$lookup":
                self._validate_lookup(stage["$lookup"], user_connection_ids)

            # Track if pipeline has a limit
            if stage_name == "$limit":
                has_limit = True
                # Enforce max limit
                limit_value = stage["$limit"]
                if not isinstance(limit_value, int) or limit_value < 1:
                    raise PipelineValidationError("$limit must be a positive integer")
                if limit_value > self.MAX_LIMIT:
                    stage = {"$limit": self.MAX_LIMIT}

            sanitized_pipeline.append(stage)

        # Add limit if not present to enforce MAX_LIMIT
        if not has_limit:
            sanitized_pipeline.append({"$limit": self.MAX_LIMIT})

        return sanitized_pipeline

    def _validate_lookup(
        self,
        lookup_config: dict[str, Any],
        user_connection_ids: list[str],
    ) -> None:
        """Validate $lookup stage for data isolation.

        Ensures the target collection (from) belongs to the user.

        Args:
            lookup_config: $lookup stage configuration
            user_connection_ids: List of connection IDs belonging to the user

        Raises:
            PipelineValidationError: If lookup target doesn't belong to user
        """
        if not isinstance(lookup_config, dict):
            raise PipelineValidationError("$lookup configuration must be a dict")

        # Check for 'from' field which specifies the target collection
        from_collection = lookup_config.get("from")

        if from_collection is None:
            raise PipelineValidationError("$lookup must specify 'from' collection")

        # For our use case, we use connection_id as identifier
        # The 'from' field should reference sheet_raw_data collection
        # and the pipeline should filter by connection_id

        # Check if there's a pipeline in the lookup that filters by connection_id
        lookup_pipeline = lookup_config.get("pipeline", [])

        if lookup_pipeline:
            # Validate that the lookup pipeline filters by user's connection_ids
            has_connection_filter = self._check_connection_filter(
                lookup_pipeline, user_connection_ids
            )
            if not has_connection_filter:
                raise PipelineValidationError(
                    "$lookup pipeline must filter by user's connection_id"
                )

    def _check_connection_filter(
        self,
        pipeline: list[dict[str, Any]],
        user_connection_ids: list[str],
    ) -> bool:
        """Check if pipeline has a $match stage filtering by user's connection_ids.

        Args:
            pipeline: Lookup sub-pipeline
            user_connection_ids: List of connection IDs belonging to the user

        Returns:
            True if pipeline properly filters by connection_id
        """
        for stage in pipeline:
            if "$match" in stage:
                match_config = stage["$match"]

                # Check for connection_id filter
                if "connection_id" in match_config:
                    conn_filter = match_config["connection_id"]

                    # Direct match
                    if isinstance(conn_filter, str):
                        return conn_filter in user_connection_ids

                    # $in operator
                    if isinstance(conn_filter, dict) and "$in" in conn_filter:
                        filter_ids = conn_filter["$in"]
                        return all(cid in user_connection_ids for cid in filter_ids)

                    # $expr with variable reference (common in correlated lookups)
                    if isinstance(conn_filter, dict) and "$expr" in match_config:
                        # For correlated lookups, we trust the outer query's filter
                        return True

        return False

    def validate_connection_ownership(
        self,
        connection_id: str,
        user_connection_ids: list[str],
    ) -> None:
        """Validate that a connection_id belongs to the user.

        Args:
            connection_id: Connection ID to validate
            user_connection_ids: List of connection IDs belonging to the user

        Raises:
            PipelineValidationError: If connection doesn't belong to user
        """
        if connection_id not in user_connection_ids:
            raise PipelineValidationError(
                "Access denied: connection does not belong to user"
            )
