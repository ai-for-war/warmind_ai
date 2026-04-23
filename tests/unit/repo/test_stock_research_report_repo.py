from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId
import pytest
from pymongo import DESCENDING, ReturnDocument

from app.domain.models.stock_research_report import (
    StockResearchReport,
    StockResearchReportFailure,
    StockResearchReportSource,
    StockResearchReportStatus,
)
from app.repo.stock_research_report_repo import StockResearchReportRepository


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _report_document(
    *,
    report_id: str | None = None,
    user_id: str = "user-1",
    organization_id: str = "org-1",
    symbol: str = "FPT",
    status: StockResearchReportStatus = StockResearchReportStatus.QUEUED,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    updated_at: datetime | None = None,
    content: str | None = None,
    sources: list[StockResearchReportSource] | None = None,
    error: StockResearchReportFailure | None = None,
) -> dict[str, object]:
    now = created_at or _utc(2026, 4, 22, 8)
    report = StockResearchReport(
        _id=report_id or str(ObjectId()),
        user_id=user_id,
        organization_id=organization_id,
        symbol=symbol,
        status=status,
        content=content,
        sources=sources or [],
        error=error,
        created_at=now,
        started_at=started_at,
        completed_at=completed_at,
        updated_at=updated_at or now,
    )
    payload = report.model_dump(by_alias=True, mode="python")
    payload["_id"] = ObjectId(payload["_id"])
    return payload


def _matches_query(document: dict[str, object], query: dict[str, object]) -> bool:
    for field_name, expected in query.items():
        if document.get(field_name) != expected:
            return False
    return True


class _FakeCursor:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = list(documents)
        self._iterator: iter[dict[str, object]] | None = None

    def sort(self, field_name: str, direction: int) -> "_FakeCursor":
        reverse = direction in {DESCENDING, -1}
        self._documents.sort(
            key=lambda document: document.get(field_name),
            reverse=reverse,
        )
        return self

    def skip(self, count: int) -> "_FakeCursor":
        self._documents = self._documents[count:]
        return self

    def limit(self, count: int) -> "_FakeCursor":
        self._documents = self._documents[:count]
        return self

    def __aiter__(self) -> "_FakeCursor":
        self._iterator = iter(self._documents)
        return self

    async def __anext__(self) -> dict[str, object]:
        if self._iterator is None:
            self._iterator = iter(self._documents)
        try:
            return deepcopy(next(self._iterator))
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCollection:
    def __init__(self, documents: list[dict[str, object]] | None = None) -> None:
        self._documents = [deepcopy(document) for document in (documents or [])]

    async def insert_one(self, payload: dict[str, object]):
        document = deepcopy(payload)
        document["_id"] = ObjectId()
        self._documents.append(document)
        return SimpleNamespace(inserted_id=document["_id"])

    async def find_one(self, query: dict[str, object]) -> dict[str, object] | None:
        for document in self._documents:
            if _matches_query(document, query):
                return deepcopy(document)
        return None

    async def find_one_and_update(
        self,
        query: dict[str, object],
        update: dict[str, dict[str, object]],
        *,
        return_document: ReturnDocument,
    ) -> dict[str, object] | None:
        for index, document in enumerate(self._documents):
            if not _matches_query(document, query):
                continue

            updated = deepcopy(document)
            updated.update(update.get("$set", {}))
            self._documents[index] = updated
            if return_document == ReturnDocument.AFTER:
                return deepcopy(updated)
            return deepcopy(document)
        return None

    def find(self, query: dict[str, object]) -> _FakeCursor:
        matched = [
            deepcopy(document)
            for document in self._documents
            if _matches_query(document, query)
        ]
        return _FakeCursor(matched)

    async def count_documents(self, query: dict[str, object]) -> int:
        return sum(1 for document in self._documents if _matches_query(document, query))


class _FakeDB:
    def __init__(self, documents: list[dict[str, object]] | None = None) -> None:
        self.stock_research_reports = _FakeCollection(documents)


@pytest.mark.asyncio
async def test_create_persists_queued_report_with_default_artifacts() -> None:
    repository = StockResearchReportRepository(_FakeDB())

    report = await repository.create(
        user_id="user-1",
        organization_id="org-1",
        symbol="fpt",
    )

    assert report.id is not None
    assert report.symbol == "FPT"
    assert report.status == StockResearchReportStatus.QUEUED
    assert report.content is None
    assert report.sources == []
    assert report.error is None


@pytest.mark.asyncio
async def test_find_owned_report_scopes_by_user_and_organization() -> None:
    owned = _report_document(
        user_id="user-1",
        organization_id="org-1",
        symbol="FPT",
    )
    repository = StockResearchReportRepository(
        _FakeDB(
            [
                owned,
                _report_document(
                    user_id="user-2",
                    organization_id="org-1",
                    symbol="VCB",
                ),
            ]
        )
    )

    found = await repository.find_owned_report(
        report_id=str(owned["_id"]),
        user_id="user-1",
        organization_id="org-1",
    )
    missing = await repository.find_owned_report(
        report_id=str(owned["_id"]),
        user_id="user-2",
        organization_id="org-1",
    )

    assert found is not None
    assert found.symbol == "FPT"
    assert missing is None


@pytest.mark.asyncio
async def test_update_lifecycle_state_updates_artifacts_and_failure_metadata() -> None:
    created_at = _utc(2026, 4, 22, 8)
    source = StockResearchReportSource(
        source_id="S1",
        url="https://example.com/fpt",
        title="Example Source",
    )
    error = StockResearchReportFailure(
        code="RuntimeError",
        message="tool failed",
    )
    existing = _report_document(
        report_id="6807dd18c5d8d14d4af1d111",
        created_at=created_at,
        updated_at=created_at,
    )
    repository = StockResearchReportRepository(_FakeDB([existing]))

    updated = await repository.update_lifecycle_state(
        report_id="6807dd18c5d8d14d4af1d111",
        status=StockResearchReportStatus.FAILED,
        started_at=_utc(2026, 4, 22, 9),
        completed_at=_utc(2026, 4, 22, 10),
        content="  Final report body  ",
        sources=[source],
        error=error,
    )

    assert updated is not None
    assert updated.status == StockResearchReportStatus.FAILED
    assert updated.content == "Final report body"
    assert updated.sources == [source]
    assert updated.error == error
    assert updated.started_at == _utc(2026, 4, 22, 9)
    assert updated.completed_at == _utc(2026, 4, 22, 10)
    assert updated.updated_at.tzinfo == timezone.utc
    assert updated.updated_at != created_at


@pytest.mark.asyncio
async def test_list_by_user_and_organization_filters_symbol_sorts_latest_first_and_paginates() -> None:
    repository = StockResearchReportRepository(
        _FakeDB(
            [
                _report_document(
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="FPT",
                    created_at=_utc(2026, 4, 20, 9),
                ),
                _report_document(
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="fpt",
                    created_at=_utc(2026, 4, 22, 9),
                ),
                _report_document(
                    user_id="user-1",
                    organization_id="org-1",
                    symbol="VCB",
                    created_at=_utc(2026, 4, 21, 9),
                ),
                _report_document(
                    user_id="user-1",
                    organization_id="org-2",
                    symbol="FPT",
                    created_at=_utc(2026, 4, 23, 9),
                ),
            ]
        )
    )

    reports, total = await repository.list_by_user_and_organization(
        user_id="user-1",
        organization_id="org-1",
        symbol=" fpt ",
        page=1,
        page_size=1,
    )

    assert total == 2
    assert [report.symbol for report in reports] == ["FPT"]
    assert [report.created_at for report in reports] == [
        _utc(2026, 4, 22, 9),
    ]
