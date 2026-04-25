"""Repository for stock research report persistence operations."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING, ReturnDocument

from app.domain.models.stock_research_report import (
    StockResearchReport,
    StockResearchReportFailure,
    StockResearchReportRuntimeConfig,
    StockResearchReportSource,
    StockResearchReportStatus,
    StockResearchReportTriggerType,
)

_UNSET = object()


class StockResearchReportRepository:
    """Database access wrapper for persisted stock research reports."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.stock_research_reports

    async def create(
        self,
        *,
        user_id: str,
        organization_id: str,
        symbol: str,
        status: StockResearchReportStatus = StockResearchReportStatus.QUEUED,
        trigger_type: StockResearchReportTriggerType = (
            StockResearchReportTriggerType.MANUAL
        ),
        schedule_id: str | None = None,
        schedule_run_id: str | None = None,
        runtime_config: StockResearchReportRuntimeConfig | None = None,
        content: str | None = None,
        sources: list[StockResearchReportSource] | None = None,
        error: StockResearchReportFailure | None = None,
    ) -> StockResearchReport:
        """Create one stock research report document with sensible defaults."""
        now = datetime.now(timezone.utc)
        payload = StockResearchReport(
            user_id=user_id,
            organization_id=organization_id,
            symbol=symbol,
            status=status,
            trigger_type=trigger_type,
            schedule_id=schedule_id,
            schedule_run_id=schedule_run_id,
            runtime_config=runtime_config,
            content=content,
            sources=sources or [],
            error=error,
            created_at=now,
            started_at=None,
            completed_at=None,
            updated_at=now,
        ).model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)
        return StockResearchReport(**payload)

    async def update_lifecycle_state(
        self,
        *,
        report_id: str,
        status: StockResearchReportStatus,
        started_at: datetime | None | object = _UNSET,
        completed_at: datetime | None | object = _UNSET,
        content: str | None | object = _UNSET,
        sources: list[StockResearchReportSource] | None | object = _UNSET,
        error: StockResearchReportFailure | None | object = _UNSET,
    ) -> StockResearchReport | None:
        """Update lifecycle state and related artifact fields for one report."""
        object_id = _parse_object_id(report_id)
        if object_id is None:
            return None

        update_fields: dict[str, object] = {
            "status": status.value,
            "updated_at": datetime.now(timezone.utc),
        }
        if started_at is not _UNSET:
            update_fields["started_at"] = started_at
        if completed_at is not _UNSET:
            update_fields["completed_at"] = completed_at
        if content is not _UNSET:
            if content is None:
                update_fields["content"] = None
            else:
                normalized_content = content.strip()
                update_fields["content"] = normalized_content or None
        if sources is not _UNSET:
            update_fields["sources"] = [
                source.model_dump() for source in (sources or [])
            ]
        if error is not _UNSET:
            update_fields["error"] = None if error is None else error.model_dump()

        document = await self.collection.find_one_and_update(
            {"_id": object_id},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def find_by_id(self, report_id: str) -> StockResearchReport | None:
        """Find one stock research report by id without caller scope filtering."""
        object_id = _parse_object_id(report_id)
        if object_id is None:
            return None

        document = await self.collection.find_one({"_id": object_id})
        return self._to_model(document)

    async def claim_queued_report(self, report_id: str) -> StockResearchReport | None:
        """Atomically claim one queued report for worker processing."""
        object_id = _parse_object_id(report_id)
        if object_id is None:
            return None

        now = datetime.now(timezone.utc)
        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": StockResearchReportStatus.QUEUED.value,
            },
            {
                "$set": {
                    "status": StockResearchReportStatus.RUNNING.value,
                    "started_at": now,
                    "completed_at": None,
                    "error": None,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def find_owned_report(
        self,
        *,
        report_id: str,
        user_id: str,
        organization_id: str,
    ) -> StockResearchReport | None:
        """Find one owned stock research report by id and caller scope."""
        object_id = _parse_object_id(report_id)
        if object_id is None:
            return None

        document = await self.collection.find_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
            }
        )
        return self._to_model(document)

    async def list_by_user_and_organization(
        self,
        *,
        user_id: str,
        organization_id: str,
        symbol: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockResearchReport], int]:
        """List a user's stock research reports inside one organization."""
        query: dict[str, object] = {
            "user_id": user_id,
            "organization_id": organization_id,
        }
        normalized_symbol = (symbol or "").strip().upper()
        if normalized_symbol:
            query["symbol"] = normalized_symbol

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
            [self._to_model(document) for document in documents if document is not None],
            total,
        )

    @staticmethod
    def _to_model(document: dict[str, object] | None) -> StockResearchReport | None:
        """Convert one MongoDB document into a typed stock research report model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return StockResearchReport(**payload)


def _parse_object_id(value: str) -> ObjectId | None:
    """Parse one string id into ObjectId when valid."""
    try:
        return ObjectId(value)
    except (TypeError, ValueError, InvalidId):
        return None
