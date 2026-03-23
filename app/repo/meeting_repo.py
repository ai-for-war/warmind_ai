"""Repository for meeting transcript session persistence."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING, ReturnDocument

from app.domain.models.meeting import Meeting, MeetingArchiveScope, MeetingStatus


class MeetingRepository:
    """Database access wrapper for durable meeting sessions."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.meetings

    async def create(
        self,
        *,
        organization_id: str,
        created_by: str,
        stream_id: str,
        title: str | None = None,
        source: str = "google_meet",
        status: MeetingStatus | str = MeetingStatus.STREAMING,
        language: str | None = None,
        meeting_id: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        error_message: str | None = None,
    ) -> Meeting:
        """Create or return a durable meeting session record."""
        document = {
            "_id": meeting_id or uuid4().hex,
            "organization_id": organization_id,
            "created_by": created_by,
            "title": title,
            "source": self._normalize_source(source),
            "status": self._normalize_status(status),
            "language": language,
            "stream_id": stream_id,
            "started_at": started_at or datetime.now(timezone.utc),
            "ended_at": ended_at,
            "error_message": error_message,
            "archived_at": None,
            "archived_by": None,
        }
        persisted = await self.collection.find_one_and_update(
            {"_id": document["_id"]},
            {"$setOnInsert": document},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return Meeting(**persisted)

    async def get_by_id(self, *, meeting_id: str) -> Meeting | None:
        """Get a meeting session by its durable id."""
        document = await self.collection.find_one({"_id": meeting_id})
        if document is None:
            return None
        return Meeting(**document)

    async def get_by_stream_id(
        self,
        *,
        stream_id: str,
        organization_id: str | None = None,
    ) -> Meeting | None:
        """Get the most recent meeting session for a provider stream id."""
        query: dict[str, str] = {"stream_id": stream_id}
        if organization_id is not None:
            query["organization_id"] = organization_id

        document = await self.collection.find_one(query)
        if document is None:
            return None
        return Meeting(**document)

    async def list_by_organization(
        self,
        *,
        organization_id: str,
        limit: int = 50,
    ) -> list[Meeting]:
        """List recent meetings for one organization."""
        cursor = (
            self.collection.find({"organization_id": organization_id})
            .sort([("started_at", DESCENDING)])
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [Meeting(**document) for document in documents]

    async def list_by_creator(
        self,
        *,
        created_by: str,
        organization_id: str,
        limit: int = 50,
    ) -> list[Meeting]:
        """List recent meetings created by one user within an organization."""
        cursor = (
            self.collection.find(
                {
                    "created_by": created_by,
                    "organization_id": organization_id,
                }
            )
            .sort([("started_at", DESCENDING)])
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [Meeting(**document) for document in documents]

    async def list_by_status(
        self,
        *,
        status: MeetingStatus | str,
        limit: int = 50,
    ) -> list[Meeting]:
        """List recent meetings by durable lifecycle state."""
        cursor = (
            self.collection.find({"status": self._normalize_status(status)})
            .sort([("started_at", DESCENDING)])
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [Meeting(**document) for document in documents]

    async def list_for_creator(
        self,
        *,
        organization_id: str,
        created_by: str,
        scope: MeetingArchiveScope | str = MeetingArchiveScope.ACTIVE,
        status: MeetingStatus | str | None = None,
        started_at_from: datetime | None = None,
        started_at_to: datetime | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Meeting]:
        """List creator-scoped meetings with archive and metadata filters."""
        cursor = (
            self.collection.find(
                self._build_creator_query(
                    organization_id=organization_id,
                    created_by=created_by,
                    scope=scope,
                    status=status,
                    started_at_from=started_at_from,
                    started_at_to=started_at_to,
                    q=q,
                )
            )
            .sort([("started_at", DESCENDING), ("_id", DESCENDING)])
            .skip(skip)
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [Meeting(**document) for document in documents]

    async def count_for_creator(
        self,
        *,
        organization_id: str,
        created_by: str,
        scope: MeetingArchiveScope | str = MeetingArchiveScope.ACTIVE,
        status: MeetingStatus | str | None = None,
        started_at_from: datetime | None = None,
        started_at_to: datetime | None = None,
        q: str | None = None,
    ) -> int:
        """Count creator-scoped meetings matching the provided filters."""
        return await self.collection.count_documents(
            self._build_creator_query(
                organization_id=organization_id,
                created_by=created_by,
                scope=scope,
                status=status,
                started_at_from=started_at_from,
                started_at_to=started_at_to,
                q=q,
            )
        )

    async def get_for_creator(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        created_by: str,
    ) -> Meeting | None:
        """Get one owned meeting within the current organization scope."""
        document = await self.collection.find_one(
            {
                "_id": meeting_id,
                "organization_id": organization_id,
                "created_by": created_by,
            }
        )
        if document is None:
            return None
        return Meeting(**document)

    async def update_metadata_for_creator(
        self,
        *,
        meeting_id: str,
        organization_id: str,
        created_by: str,
        title: str | None = None,
        source: str | None = None,
        archived: bool | None = None,
        archived_by: str | None = None,
        archived_at: datetime | None = None,
    ) -> Meeting | None:
        """Update owned meeting metadata and archive state."""
        update_set: dict[str, object | None] = {}
        update_unset: dict[str, str] = {}

        if title is not None:
            update_set["title"] = title
        if source is not None:
            update_set["source"] = self._normalize_source(source)
        if archived is True:
            update_set["archived_at"] = archived_at or datetime.now(timezone.utc)
            update_set["archived_by"] = archived_by
        elif archived is False:
            update_unset["archived_at"] = ""
            update_unset["archived_by"] = ""

        if not update_set and not update_unset:
            return await self.get_for_creator(
                meeting_id=meeting_id,
                organization_id=organization_id,
                created_by=created_by,
            )

        update_document: dict[str, dict[str, object]] = {}
        if update_set:
            update_document["$set"] = update_set
        if update_unset:
            update_document["$unset"] = update_unset

        document = await self.collection.find_one_and_update(
            {
                "_id": meeting_id,
                "organization_id": organization_id,
                "created_by": created_by,
            },
            update_document,
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return Meeting(**document)

    async def update_status(
        self,
        *,
        meeting_id: str,
        status: MeetingStatus | str,
        ended_at: datetime | None = None,
        error_message: str | None = None,
    ) -> Meeting | None:
        """Update the durable lifecycle state of a meeting session."""
        update_fields: dict[str, object | None] = {
            "status": self._normalize_status(status),
        }
        if ended_at is not None:
            update_fields["ended_at"] = ended_at
        if error_message is not None:
            update_fields["error_message"] = error_message

        document = await self.collection.find_one_and_update(
            {"_id": meeting_id},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return Meeting(**document)

    @staticmethod
    def _normalize_status(status: MeetingStatus | str) -> str:
        if isinstance(status, MeetingStatus):
            return status.value
        return status

    @staticmethod
    def _normalize_scope(scope: MeetingArchiveScope | str) -> str:
        if isinstance(scope, MeetingArchiveScope):
            return scope.value
        return scope

    @staticmethod
    def _normalize_source(source: str) -> str:
        normalized = source.strip().lower()
        return normalized or "google_meet"

    def _build_creator_query(
        self,
        *,
        organization_id: str,
        created_by: str,
        scope: MeetingArchiveScope | str,
        status: MeetingStatus | str | None,
        started_at_from: datetime | None,
        started_at_to: datetime | None,
        q: str | None,
    ) -> dict[str, object]:
        query: dict[str, object] = {
            "organization_id": organization_id,
            "created_by": created_by,
        }

        normalized_scope = self._normalize_scope(scope)
        if normalized_scope == MeetingArchiveScope.ACTIVE.value:
            query["archived_at"] = None
        elif normalized_scope == MeetingArchiveScope.ARCHIVED.value:
            query["archived_at"] = {"$ne": None}

        if status is not None:
            query["status"] = self._normalize_status(status)

        if started_at_from is not None or started_at_to is not None:
            started_at_query: dict[str, datetime] = {}
            if started_at_from is not None:
                started_at_query["$gte"] = started_at_from
            if started_at_to is not None:
                started_at_query["$lte"] = started_at_to
            query["started_at"] = started_at_query

        normalized_query = (q or "").strip()
        if normalized_query:
            query["title"] = {
                "$regex": re.escape(normalized_query),
                "$options": "i",
            }

        return query
