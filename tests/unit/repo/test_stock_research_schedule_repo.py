from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from bson import ObjectId
import pytest
from pymongo import DESCENDING

from app.domain.models.stock_research_report import StockResearchReportRuntimeConfig
from app.domain.models.stock_research_schedule import (
    StockResearchSchedule,
    StockResearchScheduleStatus,
    StockResearchScheduleType,
)
from app.repo.stock_research_schedule_repo import StockResearchScheduleRepository


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _runtime_config() -> StockResearchReportRuntimeConfig:
    return StockResearchReportRuntimeConfig(
        provider="openai",
        model="gpt-5.2",
        reasoning="high",
    )


def _schedule_document(
    *,
    schedule_id: str | None = None,
    user_id: str = "user-1",
    organization_id: str = "org-1",
    symbol: str = "FPT",
    status: StockResearchScheduleStatus = StockResearchScheduleStatus.ACTIVE,
    created_at: datetime | None = None,
) -> dict[str, object]:
    now = created_at or _utc(2026, 4, 24, 8)
    schedule = StockResearchSchedule(
        _id=schedule_id or str(ObjectId()),
        user_id=user_id,
        organization_id=organization_id,
        symbol=symbol,
        runtime_config=_runtime_config(),
        schedule_type=StockResearchScheduleType.DAILY,
        hour=8,
        weekdays=[],
        status=status,
        next_run_at=_utc(2026, 4, 25, 1),
        created_at=now,
        updated_at=now,
    )
    payload = schedule.model_dump(by_alias=True, mode="python")
    payload["_id"] = ObjectId(payload["_id"])
    return payload


def _matches_query(document: dict[str, object], query: dict[str, object]) -> bool:
    for field_name, expected in query.items():
        actual = document.get(field_name)
        if isinstance(expected, dict) and "$ne" in expected:
            if actual == expected["$ne"]:
                return False
            continue
        if actual != expected:
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
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = [deepcopy(document) for document in documents]

    def find(self, query: dict[str, object]) -> _FakeCursor:
        return _FakeCursor(
            [
                deepcopy(document)
                for document in self._documents
                if _matches_query(document, query)
            ]
        )

    async def count_documents(self, query: dict[str, object]) -> int:
        return sum(1 for document in self._documents if _matches_query(document, query))


class _FakeDB:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.stock_research_schedules = _FakeCollection(documents)


@pytest.mark.asyncio
async def test_list_by_user_and_organization_filters_sorts_and_paginates() -> None:
    repository = StockResearchScheduleRepository(
        _FakeDB(
            [
                _schedule_document(
                    schedule_id="6807dd18c5d8d14d4af1d111",
                    symbol="FPT",
                    created_at=_utc(2026, 4, 20, 8),
                ),
                _schedule_document(
                    schedule_id="6807dd18c5d8d14d4af1d112",
                    symbol="VCB",
                    created_at=_utc(2026, 4, 22, 8),
                ),
                _schedule_document(
                    schedule_id="6807dd18c5d8d14d4af1d113",
                    symbol="SSI",
                    created_at=_utc(2026, 4, 21, 8),
                ),
                _schedule_document(
                    schedule_id="6807dd18c5d8d14d4af1d114",
                    user_id="user-2",
                    symbol="HPG",
                    created_at=_utc(2026, 4, 23, 8),
                ),
                _schedule_document(
                    schedule_id="6807dd18c5d8d14d4af1d115",
                    symbol="MSN",
                    status=StockResearchScheduleStatus.DELETED,
                    created_at=_utc(2026, 4, 24, 8),
                ),
            ]
        )
    )

    schedules, total = await repository.list_by_user_and_organization(
        user_id="user-1",
        organization_id="org-1",
        page=2,
        page_size=1,
    )

    assert total == 3
    assert [schedule.symbol for schedule in schedules] == ["SSI"]
