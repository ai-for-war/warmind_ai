"""Repositories for sandbox trade-agent persistence operations."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.domain.models.sandbox_trade_agent import (
    SandboxTradeAgentRuntimeConfig,
    SandboxTradeMarketSnapshot,
    SandboxTradeOrder,
    SandboxTradePortfolioSnapshot,
    SandboxTradePosition,
    SandboxTradeSession,
    SandboxTradeSessionStatus,
    SandboxTradeSettlement,
    SandboxTradeSettlementStatus,
    SandboxTradeTick,
    SandboxTradeTickStatus,
)

_UNSET = object()


class SandboxTradeSessionRepository:
    """Database access wrapper for user-owned sandbox trade sessions."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.sandbox_trade_sessions

    async def create(
        self,
        *,
        user_id: str,
        organization_id: str,
        symbol: str,
        initial_capital: float,
        next_run_at: datetime,
        runtime_config: SandboxTradeAgentRuntimeConfig | None = None,
        status: SandboxTradeSessionStatus = SandboxTradeSessionStatus.ACTIVE,
    ) -> SandboxTradeSession:
        """Create one sandbox trade-agent session."""
        now = datetime.now(timezone.utc)
        payload = SandboxTradeSession(
            user_id=user_id,
            organization_id=organization_id,
            symbol=symbol,
            status=status,
            initial_capital=initial_capital,
            runtime_config=runtime_config,
            next_run_at=next_run_at,
            created_at=now,
            updated_at=now,
        ).model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)
        return SandboxTradeSession(**payload)

    async def find_owned_session(
        self,
        *,
        session_id: str,
        user_id: str,
        organization_id: str,
    ) -> SandboxTradeSession | None:
        """Find one non-deleted session by id and caller scope."""
        object_id = _parse_object_id(session_id)
        if object_id is None:
            return None

        document = await self.collection.find_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "status": {"$ne": SandboxTradeSessionStatus.DELETED.value},
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
    ) -> tuple[list[SandboxTradeSession], int]:
        """List one user's non-deleted sessions inside one organization."""
        query: dict[str, object] = {
            "user_id": user_id,
            "organization_id": organization_id,
            "status": {"$ne": SandboxTradeSessionStatus.DELETED.value},
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
        return [self._to_model(document) for document in documents if document], total

    async def list_due_active_sessions(
        self,
        *,
        due_at: datetime,
        limit: int = 100,
    ) -> list[SandboxTradeSession]:
        """List active sessions whose next sandbox tick is due."""
        cursor = (
            self.collection.find(
                {
                    "status": SandboxTradeSessionStatus.ACTIVE.value,
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
        session_id: str,
        expected_next_run_at: datetime,
        next_run_at: datetime,
        last_tick_at: datetime | None | object = _UNSET,
    ) -> SandboxTradeSession | None:
        """Advance one active session if its due occurrence has not changed."""
        object_id = _parse_object_id(session_id)
        if object_id is None:
            return None

        update_fields: dict[str, object] = {
            "next_run_at": next_run_at,
            "updated_at": datetime.now(timezone.utc),
        }
        if last_tick_at is not _UNSET:
            update_fields["last_tick_at"] = last_tick_at

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": SandboxTradeSessionStatus.ACTIVE.value,
                "next_run_at": expected_next_run_at,
            },
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def update_owned_session(
        self,
        *,
        session_id: str,
        user_id: str,
        organization_id: str,
        status: SandboxTradeSessionStatus | object = _UNSET,
        runtime_config: SandboxTradeAgentRuntimeConfig | None | object = _UNSET,
        next_run_at: datetime | object = _UNSET,
        last_tick_at: datetime | None | object = _UNSET,
        deleted_at: datetime | None | object = _UNSET,
    ) -> SandboxTradeSession | None:
        """Update one caller-owned non-deleted session."""
        object_id = _parse_object_id(session_id)
        if object_id is None:
            return None

        update_fields: dict[str, object] = {"updated_at": datetime.now(timezone.utc)}
        if status is not _UNSET:
            update_fields["status"] = status.value
        if runtime_config is not _UNSET:
            update_fields["runtime_config"] = (
                None if runtime_config is None else runtime_config.model_dump()
            )
        if next_run_at is not _UNSET:
            update_fields["next_run_at"] = next_run_at
        if last_tick_at is not _UNSET:
            update_fields["last_tick_at"] = last_tick_at
        if deleted_at is not _UNSET:
            update_fields["deleted_at"] = deleted_at

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "status": {"$ne": SandboxTradeSessionStatus.DELETED.value},
            },
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def soft_delete_owned_session(
        self,
        *,
        session_id: str,
        user_id: str,
        organization_id: str,
    ) -> SandboxTradeSession | None:
        """Mark one caller-owned session as deleted."""
        now = datetime.now(timezone.utc)
        return await self.update_owned_session(
            session_id=session_id,
            user_id=user_id,
            organization_id=organization_id,
            status=SandboxTradeSessionStatus.DELETED,
            deleted_at=now,
        )

    @staticmethod
    def _to_model(document: dict[str, object] | None) -> SandboxTradeSession | None:
        """Convert one MongoDB document into a typed session model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return SandboxTradeSession(**payload)


class SandboxTradeTickRepository:
    """Database access wrapper for sandbox trade tick records."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.sandbox_trade_ticks

    async def create_dispatching(
        self,
        *,
        session_id: str,
        tick_at: datetime,
        lock_expires_at: datetime,
    ) -> SandboxTradeTick | None:
        """Create one idempotent dispatching tick or return None on duplicate."""
        now = datetime.now(timezone.utc)
        payload = SandboxTradeTick(
            session_id=session_id,
            tick_at=tick_at,
            status=SandboxTradeTickStatus.DISPATCHING,
            lock_expires_at=lock_expires_at,
            lock_token=str(uuid4()),
            created_at=now,
            updated_at=now,
        ).model_dump(by_alias=True, exclude={"id"})

        try:
            result = await self.collection.insert_one(payload)
        except DuplicateKeyError:
            return None

        payload["_id"] = str(result.inserted_id)
        return SandboxTradeTick(**payload)

    async def claim_stale_dispatch(
        self,
        *,
        session_id: str,
        tick_at: datetime,
        now: datetime,
        lock_expires_at: datetime,
    ) -> SandboxTradeTick | None:
        """Refresh and reclaim a stale non-terminal tick dispatch lock."""
        document = await self.collection.find_one_and_update(
            {
                "session_id": session_id,
                "tick_at": tick_at,
                "status": {
                    "$in": [
                        SandboxTradeTickStatus.DISPATCHING.value,
                        SandboxTradeTickStatus.RUNNING.value,
                    ]
                },
                "lock_expires_at": {"$lte": now},
            },
            {
                "$set": {
                    "status": SandboxTradeTickStatus.DISPATCHING.value,
                    "lock_expires_at": lock_expires_at,
                    "lock_token": str(uuid4()),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def claim_for_processing(
        self,
        *,
        tick_id: str,
        lock_token: str,
        now: datetime,
        lock_expires_at: datetime,
    ) -> SandboxTradeTick | None:
        """Move a queued dispatch tick to running for one worker owner."""
        object_id = _parse_object_id(tick_id)
        if object_id is None:
            return None

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": SandboxTradeTickStatus.DISPATCHING.value,
                "lock_token": lock_token,
                "lock_expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "status": SandboxTradeTickStatus.RUNNING.value,
                    "started_at": now,
                    "lock_expires_at": lock_expires_at,
                    "lock_token": str(uuid4()),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def release_dispatch_after_enqueue_failure(
        self,
        *,
        tick_id: str,
        lock_token: str,
        now: datetime,
        error: str | None = None,
    ) -> SandboxTradeTick | None:
        """Expire one dispatch claim so a later dispatcher can retry enqueue."""
        object_id = _parse_object_id(tick_id)
        if object_id is None:
            return None

        update_fields: dict[str, object] = {
            "lock_expires_at": now,
            "updated_at": datetime.now(timezone.utc),
        }
        if error:
            update_fields["error"] = error

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": SandboxTradeTickStatus.DISPATCHING.value,
                "lock_token": lock_token,
            },
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def attach_market_snapshot(
        self,
        *,
        tick_id: str,
        lock_token: str,
        market_snapshot: SandboxTradeMarketSnapshot,
    ) -> SandboxTradeTick | None:
        """Persist a market snapshot on a running tick owned by one worker."""
        object_id = _parse_object_id(tick_id)
        if object_id is None:
            return None

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": SandboxTradeTickStatus.RUNNING.value,
                "lock_token": lock_token,
            },
            {
                "$set": {
                    "market_snapshot": market_snapshot.model_dump(mode="json"),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def mark_skipped_no_fresh_market_data(
        self,
        *,
        tick_id: str,
        lock_token: str,
        completed_at: datetime,
        skip_reason: str,
        market_snapshot: SandboxTradeMarketSnapshot | None = None,
    ) -> SandboxTradeTick | None:
        """Mark one worker-owned tick as skipped before any agent call."""
        object_id = _parse_object_id(tick_id)
        if object_id is None:
            return None

        update_fields: dict[str, object] = {
            "status": SandboxTradeTickStatus.SKIPPED.value,
            "completed_at": completed_at,
            "skip_reason": skip_reason,
            "lock_expires_at": None,
            "updated_at": datetime.now(timezone.utc),
        }
        if market_snapshot is not None:
            update_fields["market_snapshot"] = market_snapshot.model_dump(mode="json")

        document = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "status": SandboxTradeTickStatus.RUNNING.value,
                "lock_token": lock_token,
            },
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document)

    async def list_by_session(
        self,
        *,
        session_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SandboxTradeTick], int]:
        """List tick history for one sandbox session."""
        query = {"session_id": session_id}
        return await _list_paginated(
            collection=self.collection,
            query=query,
            model_factory=self._to_model,
            sort_field="tick_at",
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def _to_model(document: dict[str, object] | None) -> SandboxTradeTick | None:
        """Convert one MongoDB document into a typed tick model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return SandboxTradeTick(**payload)


class SandboxTradeOrderRepository:
    """Database access wrapper for sandbox order records."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.sandbox_trade_orders

    async def list_by_session(
        self,
        *,
        session_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SandboxTradeOrder], int]:
        """List sandbox orders for one session."""
        return await _list_paginated(
            collection=self.collection,
            query={"session_id": session_id},
            model_factory=self._to_model,
            sort_field="created_at",
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def _to_model(document: dict[str, object] | None) -> SandboxTradeOrder | None:
        """Convert one MongoDB document into a typed order model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return SandboxTradeOrder(**payload)


class SandboxTradePositionRepository:
    """Database access wrapper for current sandbox position state."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.sandbox_trade_positions

    async def create_initial(
        self,
        *,
        session_id: str,
        symbol: str,
        initial_capital: float,
    ) -> SandboxTradePosition:
        """Create initial cash-only position state for a new session."""
        now = datetime.now(timezone.utc)
        payload = SandboxTradePosition(
            session_id=session_id,
            symbol=symbol,
            available_cash=initial_capital,
            pending_cash=0,
            total_quantity=0,
            sellable_quantity=0,
            pending_quantity=0,
            average_cost=0,
            realized_pnl=0,
            created_at=now,
            updated_at=now,
        ).model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(payload)
        payload["_id"] = str(result.inserted_id)
        return SandboxTradePosition(**payload)

    async def find_by_session(
        self,
        *,
        session_id: str,
    ) -> SandboxTradePosition | None:
        """Find current position state for one session."""
        document = await self.collection.find_one({"session_id": session_id})
        return self._to_model(document)

    @staticmethod
    def _to_model(document: dict[str, object] | None) -> SandboxTradePosition | None:
        """Convert one MongoDB document into a typed position model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return SandboxTradePosition(**payload)


class SandboxTradeSettlementRepository:
    """Database access wrapper for sandbox settlement ledger records."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.sandbox_trade_settlements

    async def list_by_session(
        self,
        *,
        session_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SandboxTradeSettlement], int]:
        """List settlement history for one session."""
        return await _list_paginated(
            collection=self.collection,
            query={"session_id": session_id},
            model_factory=self._to_model,
            sort_field="created_at",
            page=page,
            page_size=page_size,
        )

    async def list_pending_by_session(
        self,
        *,
        session_id: str,
        limit: int = 100,
    ) -> list[SandboxTradeSettlement]:
        """List pending settlements for current portfolio state reads."""
        cursor = (
            self.collection.find(
                {
                    "session_id": session_id,
                    "status": SandboxTradeSettlementStatus.PENDING.value,
                }
            )
            .sort("settle_at", ASCENDING)
            .limit(limit)
        )
        documents = [document async for document in cursor]
        return [self._to_model(document) for document in documents if document]

    @staticmethod
    def _to_model(
        document: dict[str, object] | None,
    ) -> SandboxTradeSettlement | None:
        """Convert one MongoDB document into a typed settlement model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return SandboxTradeSettlement(**payload)


class SandboxTradePortfolioSnapshotRepository:
    """Database access wrapper for portfolio accounting snapshots."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db.sandbox_trade_portfolio_snapshots

    async def list_by_session(
        self,
        *,
        session_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SandboxTradePortfolioSnapshot], int]:
        """List portfolio snapshots for one session."""
        return await _list_paginated(
            collection=self.collection,
            query={"session_id": session_id},
            model_factory=self._to_model,
            sort_field="created_at",
            page=page,
            page_size=page_size,
        )

    async def find_latest_by_session(
        self,
        *,
        session_id: str,
    ) -> SandboxTradePortfolioSnapshot | None:
        """Find the latest portfolio snapshot for one session."""
        document = await self.collection.find_one(
            {"session_id": session_id},
            sort=[("created_at", DESCENDING)],
        )
        return self._to_model(document)

    @staticmethod
    def _to_model(
        document: dict[str, object] | None,
    ) -> SandboxTradePortfolioSnapshot | None:
        """Convert one MongoDB document into a typed portfolio snapshot model."""
        if document is None:
            return None
        payload = dict(document)
        payload["_id"] = str(payload["_id"])
        return SandboxTradePortfolioSnapshot(**payload)


async def _list_paginated(
    *,
    collection: object,
    query: dict[str, object],
    model_factory: object,
    sort_field: str,
    page: int,
    page_size: int,
) -> tuple[list[object], int]:
    """List one Mongo collection page and convert documents to models."""
    skip = (page - 1) * page_size
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort(sort_field, DESCENDING)
        .skip(skip)
        .limit(page_size)
    )
    documents = [document async for document in cursor]
    return [model_factory(document) for document in documents if document], total


def _parse_object_id(value: str) -> ObjectId | None:
    """Parse one string id into ObjectId when valid."""
    try:
        return ObjectId(value)
    except (TypeError, ValueError, InvalidId):
        return None
