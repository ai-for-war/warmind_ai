"""Sheet data repository for database operations."""

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.models.sheet_connection import SheetRawData


class SheetDataRepository:
    """Repository for sheet raw data database operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize SheetDataRepository with database instance.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        self.collection = db.sheet_raw_data

    async def upsert(
        self,
        connection_id: str,
        row_number: int,
        data: dict,
        raw_data: dict,
    ) -> SheetRawData:
        """Upsert a row of sheet data.

        If a document with the same connection_id and row_number exists,
        it will be updated. Otherwise, a new document will be created.

        Args:
            connection_id: Connection ID this data belongs to
            row_number: Row number in the sheet
            data: Mapped data (after column mapping)
            raw_data: Original row data

        Returns:
            Upserted SheetRawData instance
        """
        now = datetime.now(timezone.utc)

        result = await self.collection.find_one_and_update(
            {"connection_id": connection_id, "row_number": row_number},
            {
                "$set": {
                    "connection_id": connection_id,
                    "row_number": row_number,
                    "data": data,
                    "raw_data": raw_data,
                    "synced_at": now,
                },
            },
            upsert=True,
            return_document=True,
        )

        result["_id"] = str(result["_id"])
        return SheetRawData(**result)

    async def find_by_connection_id(
        self,
        connection_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SheetRawData], int]:
        """Find all sheet data for a connection with pagination.

        Args:
            connection_id: Connection ID to search for
            page: Page number (1-indexed)
            page_size: Number of records per page

        Returns:
            Tuple of (list of SheetRawData instances, total count)
        """
        # Calculate skip value
        skip = (page - 1) * page_size

        # Get total count
        total = await self.collection.count_documents({"connection_id": connection_id})

        # Get paginated results sorted by row_number
        cursor = (
            self.collection.find({"connection_id": connection_id})
            .sort("row_number", 1)
            .skip(skip)
            .limit(page_size)
        )

        data_list = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            data_list.append(SheetRawData(**doc))

        return data_list, total

    async def delete_by_connection_id(self, connection_id: str) -> int:
        """Delete all sheet data for a connection.

        Args:
            connection_id: Connection ID to delete data for

        Returns:
            Number of documents deleted
        """
        result = await self.collection.delete_many({"connection_id": connection_id})
        return result.deleted_count

    async def aggregate(self, pipeline: list[dict]) -> list[dict]:
        """Execute aggregation pipeline.

        Args:
            pipeline: MongoDB aggregation pipeline stages

        Returns:
            List of aggregation results
        """
        cursor = self.collection.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def find_with_search(
        self,
        connection_id: str,
        search: str | None,
        search_fields: list[str],
        date_field: str | None,
        date_from: "date | None",
        date_to: "date | None",
        sort_by: str | None,
        sort_order: int,
        skip: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Find documents with search, filter, and pagination.

        Args:
            connection_id: Connection ID to filter by
            search: Search query string (case-insensitive regex)
            search_fields: List of fields to search in (without 'data.' prefix)
            date_field: Field name for date filtering (without 'data.' prefix)
            date_from: Start date for filtering
            date_to: End date for filtering
            sort_by: Field to sort by (without 'data.' prefix)
            sort_order: Sort direction (1 for ascending, -1 for descending)
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            Tuple of (list of documents, total count)
        """
        query: dict = {"connection_id": connection_id}

        # Add search condition
        if search and search_fields:
            search_conditions = [
                {f"data.{field}": {"$regex": search, "$options": "i"}}
                for field in search_fields
            ]
            query["$or"] = search_conditions

        # Add date filter
        if date_field and (date_from or date_to):
            date_query: dict = {}
            if date_from:
                date_query["$gte"] = datetime.combine(date_from, datetime.min.time())
            if date_to:
                date_query["$lte"] = datetime.combine(date_to, datetime.max.time())
            query[f"data.{date_field}"] = date_query

        # Get total count
        total = await self.collection.count_documents(query)

        # Build sort field
        sort_field = f"data.{sort_by}" if sort_by else "row_number"

        # Get paginated results
        cursor = (
            self.collection.find(query)
            .sort(sort_field, sort_order)
            .skip(skip)
            .limit(limit)
        )

        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)

        return results, total
