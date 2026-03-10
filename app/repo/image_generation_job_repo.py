"""Image generation job repository for database operations."""

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from pymongo import ReturnDocument

from app.domain.models.image_generation_job import (
    ImageGenerationJob,
    ImageGenerationJobStatus,
)


class ImageGenerationJobListResult(BaseModel):
    """Paginated image generation job query result."""

    items: list[ImageGenerationJob]
    total: int


class ImageGenerationJobRepository:
    """Repository for image generation job lifecycle and history access."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize repository with database instance."""
        self.collection = db.image_generation_jobs

    async def create(self, job_data: dict[str, Any]) -> ImageGenerationJob:
        """Insert a new image generation job with sensible defaults."""
        data = dict(job_data)
        data.setdefault("status", ImageGenerationJobStatus.PENDING.value)
        data.setdefault("requested_count", 1)
        data.setdefault("retry_count", 0)
        data.setdefault("output_image_ids", [])
        data.setdefault("success_count", 0)
        data.setdefault("failed_count", 0)
        data.setdefault("provider_trace_id", None)
        data.setdefault("error_code", None)
        data.setdefault("error_message", None)
        data.setdefault("started_at", None)
        data.setdefault("completed_at", None)
        data.setdefault("cancelled_at", None)
        data.setdefault("deleted_at", None)
        data.setdefault("requested_at", datetime.now(timezone.utc))

        result = await self.collection.insert_one(data)
        data["_id"] = str(result.inserted_id)
        return ImageGenerationJob(**data)

    async def find_by_id(self, job_id: str) -> Optional[ImageGenerationJob]:
        """Find non-deleted image generation job by ID."""
        object_id = self._to_object_id(job_id)
        if object_id is None:
            return None

        doc = await self.collection.find_one({"_id": object_id, "deleted_at": None})
        return self._to_model(doc)

    async def find_by_id_and_org(
        self,
        job_id: str,
        organization_id: str,
    ) -> Optional[ImageGenerationJob]:
        """Find non-deleted image generation job by ID scoped to organization."""
        object_id = self._to_object_id(job_id)
        if object_id is None:
            return None

        doc = await self.collection.find_one(
            {
                "_id": object_id,
                "organization_id": organization_id,
                "deleted_at": None,
            }
        )
        return self._to_model(doc)

    async def list_by_organization(
        self,
        organization_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> ImageGenerationJobListResult:
        """List jobs for an organization with newest-first ordering."""
        query = {"organization_id": organization_id, "deleted_at": None}
        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query).sort("requested_at", -1).skip(skip).limit(limit)
        )

        items: list[ImageGenerationJob] = []
        async for doc in cursor:
            model = self._to_model(doc)
            if model is not None:
                items.append(model)

        return ImageGenerationJobListResult(items=items, total=total)

    async def list_by_creator_and_organization(
        self,
        organization_id: str,
        created_by: str,
        skip: int = 0,
        limit: int = 20,
    ) -> ImageGenerationJobListResult:
        """List jobs created by a user in an organization."""
        query = {
            "organization_id": organization_id,
            "created_by": created_by,
            "deleted_at": None,
        }
        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query).sort("requested_at", -1).skip(skip).limit(limit)
        )

        items: list[ImageGenerationJob] = []
        async for doc in cursor:
            model = self._to_model(doc)
            if model is not None:
                items.append(model)

        return ImageGenerationJobListResult(items=items, total=total)

    async def claim_pending_job(self, job_id: str) -> Optional[ImageGenerationJob]:
        """Atomically transition a job from pending to processing."""
        object_id = self._to_object_id(job_id)
        if object_id is None:
            return None

        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": ImageGenerationJobStatus.PENDING.value,
                "deleted_at": None,
            },
            {
                "$set": {
                    "status": ImageGenerationJobStatus.PROCESSING.value,
                    "started_at": now,
                    "cancelled_at": None,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc)

    async def cancel_pending_job(
        self,
        job_id: str,
        actor_scope: Optional[dict[str, Any]] = None,
    ) -> Optional[ImageGenerationJob]:
        """Atomically transition a job from pending to cancelled.

        `actor_scope` can include constraints such as `organization_id` and
        `created_by` to enforce caller visibility/authority.
        """
        object_id = self._to_object_id(job_id)
        if object_id is None:
            return None

        now = datetime.now(timezone.utc)
        query: dict[str, Any] = {
            "_id": object_id,
            "status": ImageGenerationJobStatus.PENDING.value,
            "deleted_at": None,
        }
        if actor_scope:
            query.update(actor_scope)

        doc = await self.collection.find_one_and_update(
            query,
            {
                "$set": {
                    "status": ImageGenerationJobStatus.CANCELLED.value,
                    "cancelled_at": now,
                    "completed_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc)

    async def mark_succeeded(
        self,
        job_id: str,
        provider_trace_id: Optional[str],
        output_image_ids: list[str],
        success_count: int = 1,
        failed_count: int = 0,
    ) -> Optional[ImageGenerationJob]:
        """Mark a processing job as succeeded and persist completion metadata."""
        object_id = self._to_object_id(job_id)
        if object_id is None:
            return None

        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": ImageGenerationJobStatus.PROCESSING.value,
                "deleted_at": None,
            },
            {
                "$set": {
                    "status": ImageGenerationJobStatus.SUCCEEDED.value,
                    "provider_trace_id": provider_trace_id,
                    "output_image_ids": output_image_ids,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "error_code": None,
                    "error_message": None,
                    "completed_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc)

    async def mark_failed(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
        provider_trace_id: Optional[str] = None,
        failed_count: int = 1,
        success_count: int = 0,
    ) -> Optional[ImageGenerationJob]:
        """Mark a processing job as failed with normalized error metadata."""
        object_id = self._to_object_id(job_id)
        if object_id is None:
            return None

        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": ImageGenerationJobStatus.PROCESSING.value,
                "deleted_at": None,
            },
            {
                "$set": {
                    "status": ImageGenerationJobStatus.FAILED.value,
                    "provider_trace_id": provider_trace_id,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "error_code": error_code,
                    "error_message": error_message,
                    "completed_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(doc)

    @staticmethod
    def _to_object_id(value: str) -> Optional[ObjectId]:
        """Safely parse string ObjectId value."""
        try:
            return ObjectId(value)
        except (TypeError, ValueError, InvalidId):
            return None

    @staticmethod
    def _to_model(doc: Optional[dict[str, Any]]) -> Optional[ImageGenerationJob]:
        """Convert MongoDB document to ImageGenerationJob model."""
        if doc is None:
            return None
        doc["_id"] = str(doc["_id"])
        return ImageGenerationJob(**doc)
