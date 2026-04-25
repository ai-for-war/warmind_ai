"""Repository for stock research schedule occurrence dispatch records."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.domain.models.stock_research_schedule import (
    StockResearchScheduleRun,
    StockResearchScheduleRunStatus,
)


class StockResearchScheduleRunRepository:
    """Database access wrapper for idempotent schedule occurrence records."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.stock_research_schedule_runs

    async def create_dispatching(
        self,
        *,
        schedule_id: str,
        occurrence_at: datetime,
        lock_expires_at: datetime,
    ) -> StockResearchScheduleRun | None:
        """Create one dispatching occurrence or return None on duplicate."""
        now = datetime.now(timezone.utc)
        payload = StockResearchScheduleRun(
            schedule_id=schedule_id,
            occurrence_at=occurrence_at,
            status=StockResearchScheduleRunStatus.DISPATCHING,
            report_id=None,
            lock_expires_at=lock_expires_at,
            created_at=now,
            updated_at=now,
        ).model_dump(by_alias=True, exclude={"id"})

        try:
            result = await self.collection.insert_one(payload)
        except DuplicateKeyError:
            return None

        payload["_id"] = str(result.inserted_id)
        return StockResearchScheduleRun(**payload)

    async def claim_stale_dispatching(
        self,
        *,
        schedule_id: str,
        occurrence_at: datetime,
        now: datetime,
        lock_expires_at: datetime,
    ) -> StockResearchScheduleRun | None:
        """Refresh and claim a stale dispatching occurrence lock."""
        document = await self.collection.find_one_and_update(
            {
                "schedule_id": schedule_id,
                "occurrence_at": occurrence_at,
                "status": StockResearchScheduleRunStatus.DISPATCHING.value,
                "lock_expires_at": {"$lte": now},
            },
            {
                "$set": {
                    "lock_expires_at": lock_expires_at,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def claim_enqueue_failed(
        self,
        *,
        schedule_id: str,
        occurrence_at: datetime,
        lock_expires_at: datetime,
    ) -> StockResearchScheduleRun | None:
        """Claim a previously failed enqueue attempt for retry."""
        document = await self.collection.find_one_and_update(
            {
                "schedule_id": schedule_id,
                "occurrence_at": occurrence_at,
                "status": StockResearchScheduleRunStatus.ENQUEUE_FAILED.value,
            },
            {
                "$set": {
                    "status": StockResearchScheduleRunStatus.DISPATCHING.value,
                    "lock_expires_at": lock_expires_at,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def mark_queued(
        self,
        *,
        run_id: str,
        report_id: str,
    ) -> StockResearchScheduleRun | None:
        """Mark one dispatching run as successfully queued."""
        return await self._mark_terminal(
            run_id=run_id,
            status=StockResearchScheduleRunStatus.QUEUED,
            report_id=report_id,
        )

    async def attach_report(
        self,
        *,
        run_id: str,
        report_id: str,
    ) -> StockResearchScheduleRun | None:
        """Attach a created report to an in-progress dispatching occurrence."""
        object_id = _parse_object_id(run_id)
        if object_id is None:
            return None

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": StockResearchScheduleRunStatus.DISPATCHING.value,
                "report_id": None,
            },
            {
                "$set": {
                    "report_id": report_id,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def mark_enqueue_failed(
        self,
        *,
        run_id: str,
        report_id: str | None = None,
    ) -> StockResearchScheduleRun | None:
        """Mark one dispatching run as failed before worker enqueue."""
        return await self._mark_terminal(
            run_id=run_id,
            status=StockResearchScheduleRunStatus.ENQUEUE_FAILED,
            report_id=report_id,
        )

    async def find_by_schedule_occurrence(
        self,
        *,
        schedule_id: str,
        occurrence_at: datetime,
    ) -> StockResearchScheduleRun | None:
        """Find one run by schedule and occurrence timestamp."""
        document = await self.collection.find_one(
            {
                "schedule_id": schedule_id,
                "occurrence_at": occurrence_at,
            }
        )
        return self._to_model(document)

    async def list_stale_dispatching(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> list[StockResearchScheduleRun]:
        """List stale dispatching runs for recovery flows."""
        cursor = (
            self.collection.find(
                {
                    "status": StockResearchScheduleRunStatus.DISPATCHING.value,
                    "lock_expires_at": {"$lte": now},
                }
            )
            .sort("lock_expires_at", ASCENDING)
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [self._to_model(document) for document in documents if document]

    async def _mark_terminal(
        self,
        *,
        run_id: str,
        status: StockResearchScheduleRunStatus,
        report_id: str | None,
    ) -> StockResearchScheduleRun | None:
        object_id = _parse_object_id(run_id)
        if object_id is None:
            return None

        update_fields: dict[str, object] = {
            "status": status.value,
            "updated_at": datetime.now(timezone.utc),
        }
        if report_id is not None:
            update_fields["report_id"] = report_id

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": StockResearchScheduleRunStatus.DISPATCHING.value,
            },
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    @staticmethod
    def _to_model(
        document: dict[str, object] | None,
    ) -> StockResearchScheduleRun | None:
        """Convert one MongoDB document into a typed schedule run model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return StockResearchScheduleRun(**payload)


def _parse_object_id(value: str) -> ObjectId | None:
    """Parse one string id into ObjectId when valid."""
    try:
        return ObjectId(value)
    except (TypeError, ValueError, InvalidId):
        return None
