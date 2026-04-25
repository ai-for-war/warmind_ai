"""Repository for stock research schedule persistence operations."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from app.domain.models.stock_research_report import StockResearchReportRuntimeConfig
from app.domain.models.stock_research_schedule import (
    StockResearchSchedule,
    StockResearchScheduleStatus,
    StockResearchScheduleType,
    StockResearchScheduleWeekday,
)

_UNSET = object()


class StockResearchScheduleRepository:
    """Database access wrapper for user-owned stock research schedules."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.stock_research_schedules

    async def create(
        self,
        *,
        user_id: str,
        organization_id: str,
        symbol: str,
        runtime_config: StockResearchReportRuntimeConfig,
        schedule_type: StockResearchScheduleType,
        next_run_at: datetime,
        hour: int | None = None,
        weekdays: list[StockResearchScheduleWeekday] | None = None,
        status: StockResearchScheduleStatus = StockResearchScheduleStatus.ACTIVE,
    ) -> StockResearchSchedule:
        """Create one recurring stock research schedule."""
        now = datetime.now(timezone.utc)
        payload = StockResearchSchedule(
            user_id=user_id,
            organization_id=organization_id,
            symbol=symbol,
            runtime_config=runtime_config,
            schedule_type=schedule_type,
            hour=hour,
            weekdays=weekdays or [],
            status=status,
            next_run_at=next_run_at,
            created_at=now,
            updated_at=now,
        ).model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)
        return StockResearchSchedule(**payload)

    async def find_owned_schedule(
        self,
        *,
        schedule_id: str,
        user_id: str,
        organization_id: str,
    ) -> StockResearchSchedule | None:
        """Find one non-deleted schedule by id and caller scope."""
        object_id = _parse_object_id(schedule_id)
        if object_id is None:
            return None

        document = await self.collection.find_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "status": {"$ne": StockResearchScheduleStatus.DELETED.value},
            }
        )
        return self._to_model(document)

    async def list_by_user_and_organization(
        self,
        *,
        user_id: str,
        organization_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockResearchSchedule], int]:
        """List one user's non-deleted schedules inside one organization."""
        query: dict[str, object] = {
            "user_id": user_id,
            "organization_id": organization_id,
            "status": {"$ne": StockResearchScheduleStatus.DELETED.value},
        }
        skip = (page - 1) * page_size
        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(page_size)
        )
        documents = [document async for document in cursor]
        return (
            [self._to_model(document) for document in documents if document],
            total,
        )

    async def update_owned_schedule(
        self,
        *,
        schedule_id: str,
        user_id: str,
        organization_id: str,
        symbol: str | object = _UNSET,
        runtime_config: StockResearchReportRuntimeConfig | object = _UNSET,
        schedule_type: StockResearchScheduleType | object = _UNSET,
        hour: int | None | object = _UNSET,
        weekdays: list[StockResearchScheduleWeekday] | object = _UNSET,
        status: StockResearchScheduleStatus | object = _UNSET,
        next_run_at: datetime | object = _UNSET,
    ) -> StockResearchSchedule | None:
        """Update one owned non-deleted schedule and return the updated document."""
        object_id = _parse_object_id(schedule_id)
        if object_id is None:
            return None

        update_fields: dict[str, object] = {"updated_at": datetime.now(timezone.utc)}
        if symbol is not _UNSET:
            update_fields["symbol"] = symbol
        if runtime_config is not _UNSET:
            update_fields["runtime_config"] = runtime_config.model_dump()
        if schedule_type is not _UNSET:
            update_fields["schedule_type"] = schedule_type.value
        if hour is not _UNSET:
            update_fields["hour"] = hour
        if weekdays is not _UNSET:
            update_fields["weekdays"] = [weekday.value for weekday in weekdays]
        if status is not _UNSET:
            update_fields["status"] = status.value
        if next_run_at is not _UNSET:
            update_fields["next_run_at"] = next_run_at

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "status": {"$ne": StockResearchScheduleStatus.DELETED.value},
            },
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def soft_delete_owned_schedule(
        self,
        *,
        schedule_id: str,
        user_id: str,
        organization_id: str,
    ) -> StockResearchSchedule | None:
        """Mark one owned schedule as deleted."""
        return await self.update_owned_schedule(
            schedule_id=schedule_id,
            user_id=user_id,
            organization_id=organization_id,
            status=StockResearchScheduleStatus.DELETED,
        )

    async def list_due_active_schedules(
        self,
        *,
        due_at: datetime,
        limit: int = 100,
    ) -> list[StockResearchSchedule]:
        """List active schedules whose next occurrence is due."""
        cursor = (
            self.collection.find(
                {
                    "status": StockResearchScheduleStatus.ACTIVE.value,
                    "next_run_at": {"$lte": due_at},
                }
            )
            .sort("next_run_at", ASCENDING)
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [self._to_model(document) for document in documents if document]

    async def advance_next_run_at(
        self,
        *,
        schedule_id: str,
        expected_next_run_at: datetime,
        next_run_at: datetime,
    ) -> StockResearchSchedule | None:
        """Advance one active schedule if its due occurrence has not changed."""
        object_id = _parse_object_id(schedule_id)
        if object_id is None:
            return None

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": StockResearchScheduleStatus.ACTIVE.value,
                "next_run_at": expected_next_run_at,
            },
            {
                "$set": {
                    "next_run_at": next_run_at,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    @staticmethod
    def _to_model(document: dict[str, object] | None) -> StockResearchSchedule | None:
        """Convert one MongoDB document into a typed schedule model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return StockResearchSchedule(**payload)


def _parse_object_id(value: str) -> ObjectId | None:
    """Parse one string id into ObjectId when valid."""
    try:
        return ObjectId(value)
    except (TypeError, ValueError, InvalidId):
        return None
