from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.models.stock_research_report import (
    StockResearchReport,
    StockResearchReportFailure,
    StockResearchReportRuntimeConfig,
    StockResearchReportStatus,
)
from app.domain.models.stock_research_schedule import (
    StockResearchSchedule,
    StockResearchScheduleRun,
    StockResearchScheduleRunStatus,
    StockResearchScheduleStatus,
    StockResearchScheduleType,
    StockResearchScheduleWeekday,
)
from app.domain.models.user import User
from app.domain.schemas.stock_research_report import (
    StockResearchReportRuntimeConfigRequest,
)
from app.domain.schemas.stock_research_schedule import (
    StockResearchScheduleCreateRequest,
    StockResearchScheduleDefinitionRequest,
)
from app.common.exceptions import StockResearchScheduleDispatchError
from app.services.stocks import stock_research_schedule_service as service_module
from app.services.stocks.stock_research_schedule_dispatcher_service import (
    StockResearchScheduleDispatcherService,
)
from app.services.stocks.stock_research_schedule_service import (
    StockResearchScheduleService,
)


def _utc(
    year: int = 2026,
    month: int = 4,
    day: int = 24,
    hour: int = 1,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _user() -> User:
    return User(
        _id="user-1",
        email="user@example.com",
        hashed_password="hashed",
        created_at=_utc(),
        updated_at=_utc(),
    )


def _runtime_config() -> StockResearchReportRuntimeConfig:
    return StockResearchReportRuntimeConfig(
        provider="openai",
        model="gpt-5.2",
        reasoning="high",
    )


def _schedule(
    *,
    schedule_id: str = "schedule-1",
    user_id: str = "user-1",
    organization_id: str = "org-1",
    symbol: str = "FPT",
    schedule_type: StockResearchScheduleType = StockResearchScheduleType.DAILY,
    hour: int | None = 8,
    weekdays: list[StockResearchScheduleWeekday] | None = None,
    status: StockResearchScheduleStatus = StockResearchScheduleStatus.ACTIVE,
    next_run_at: datetime | None = None,
) -> StockResearchSchedule:
    return StockResearchSchedule(
        _id=schedule_id,
        user_id=user_id,
        organization_id=organization_id,
        symbol=symbol,
        runtime_config=_runtime_config(),
        schedule_type=schedule_type,
        hour=hour,
        weekdays=weekdays or [],
        status=status,
        next_run_at=next_run_at or _utc(2026, 4, 24, 1),
        created_at=_utc(2026, 4, 23, 1),
        updated_at=_utc(2026, 4, 23, 1),
    )


def _report(
    *,
    report_id: str = "report-1",
    schedule_id: str = "schedule-1",
    schedule_run_id: str | None = None,
) -> StockResearchReport:
    return StockResearchReport(
        _id=report_id,
        user_id="user-1",
        organization_id="org-1",
        symbol="FPT",
        status=StockResearchReportStatus.QUEUED,
        schedule_id=schedule_id,
        schedule_run_id=schedule_run_id,
        runtime_config=_runtime_config(),
        created_at=_utc(),
        updated_at=_utc(),
    )


def _run(
    *,
    run_id: str = "6807dd18c5d8d14d4af1d111",
    schedule_id: str = "schedule-1",
    occurrence_at: datetime | None = None,
    report_id: str | None = None,
) -> StockResearchScheduleRun:
    return StockResearchScheduleRun(
        _id=run_id,
        schedule_id=schedule_id,
        occurrence_at=occurrence_at or _utc(2026, 4, 24, 1),
        status=StockResearchScheduleRunStatus.DISPATCHING,
        report_id=report_id,
        lock_expires_at=_utc(2026, 4, 24, 1, 10),
        created_at=_utc(),
        updated_at=_utc(),
    )


def _resolved_runtime_config() -> service_module.StockResearchAgentRuntimeConfig:
    return service_module.StockResearchAgentRuntimeConfig(
        provider="openai",
        model="gpt-5.2",
        reasoning="high",
    )


class _QueueService:
    def __init__(self, success: bool = True) -> None:
        self.success = success
        self.calls: list[dict[str, object]] = []

    async def enqueue_report(self, **kwargs) -> bool:
        self.calls.append(kwargs)
        return self.success

    async def enqueue_report_model(self, report: StockResearchReport) -> bool:
        self.calls.append(
            {
                "report_id": report.id,
                "symbol": report.symbol,
                "runtime_config": report.runtime_config,
            }
        )
        return self.success


@pytest.mark.asyncio
async def test_create_schedule_validates_symbol_runtime_and_persists_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule_repo = SimpleNamespace(create=AsyncMock(return_value=_schedule()))
    service = StockResearchScheduleService(
        schedule_repo=schedule_repo,
        report_repo=SimpleNamespace(),
        stock_repo=SimpleNamespace(exists_by_symbol=AsyncMock(return_value=True)),
    )
    monkeypatch.setattr(
        service_module,
        "resolve_stock_research_runtime_config",
        lambda **_: _resolved_runtime_config(),
    )

    response = await service.create_schedule(
        current_user=_user(),
        organization_id="org-1",
        request=StockResearchScheduleCreateRequest(
            symbol=" fpt ",
            runtime_config=StockResearchReportRuntimeConfigRequest(
                provider="openai",
                model="gpt-5.2",
                reasoning="high",
            ),
            schedule=StockResearchScheduleDefinitionRequest(type="daily", hour=8),
        ),
    )

    assert response.id == "schedule-1"
    schedule_repo.create.assert_awaited_once()
    create_kwargs = schedule_repo.create.await_args.kwargs
    assert create_kwargs["symbol"] == "FPT"
    assert create_kwargs["runtime_config"] == _runtime_config()
    assert create_kwargs["next_run_at"].tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_list_schedules_returns_paginated_response() -> None:
    schedule_repo = SimpleNamespace(
        list_by_user_and_organization=AsyncMock(
            return_value=([_schedule(), _schedule(schedule_id="schedule-2")], 7)
        )
    )
    service = StockResearchScheduleService(
        schedule_repo=schedule_repo,
        report_repo=SimpleNamespace(),
        stock_repo=SimpleNamespace(),
    )

    response = await service.list_schedules(
        current_user=_user(),
        organization_id="org-1",
        page=2,
        page_size=2,
    )

    schedule_repo.list_by_user_and_organization.assert_awaited_once_with(
        user_id="user-1",
        organization_id="org-1",
        page=2,
        page_size=2,
    )
    assert [item.id for item in response.items] == ["schedule-1", "schedule-2"]
    assert response.total == 7
    assert response.page == 2
    assert response.page_size == 2


@pytest.mark.asyncio
async def test_run_now_creates_report_and_enqueues_without_moving_next_run() -> None:
    queue_service = _QueueService()
    schedule = _schedule()
    schedule_repo = SimpleNamespace(
        find_owned_schedule=AsyncMock(return_value=schedule),
    )
    report_repo = SimpleNamespace(create=AsyncMock(return_value=_report()))
    service = StockResearchScheduleService(
        schedule_repo=schedule_repo,
        report_repo=report_repo,
        stock_repo=SimpleNamespace(),
        queue_service=queue_service,
    )

    response = await service.run_now(
        current_user=_user(),
        organization_id="org-1",
        schedule_id="schedule-1",
    )

    assert response.id == "report-1"
    report_repo.create.assert_awaited_once()
    assert report_repo.create.await_args.kwargs["schedule_id"] == "schedule-1"
    assert report_repo.create.await_args.kwargs["schedule_run_id"] is None
    assert queue_service.calls == [
        {
            "report_id": "report-1",
            "symbol": "FPT",
            "runtime_config": _runtime_config(),
        }
    ]


@pytest.mark.asyncio
async def test_run_now_marks_report_failed_when_enqueue_fails() -> None:
    queue_service = _QueueService(success=False)
    schedule = _schedule()
    report = _report()
    schedule_repo = SimpleNamespace(
        find_owned_schedule=AsyncMock(return_value=schedule),
    )
    report_repo = SimpleNamespace(
        create=AsyncMock(return_value=report),
        update_lifecycle_state=AsyncMock(return_value=report),
    )
    service = StockResearchScheduleService(
        schedule_repo=schedule_repo,
        report_repo=report_repo,
        stock_repo=SimpleNamespace(),
        queue_service=queue_service,
    )

    with pytest.raises(StockResearchScheduleDispatchError):
        await service.run_now(
            current_user=_user(),
            organization_id="org-1",
            schedule_id="schedule-1",
        )

    report_repo.update_lifecycle_state.assert_awaited_once()
    failure_kwargs = report_repo.update_lifecycle_state.await_args.kwargs
    assert failure_kwargs["report_id"] == "report-1"
    assert failure_kwargs["status"] == StockResearchReportStatus.FAILED
    assert failure_kwargs["content"] is None
    assert failure_kwargs["sources"] == []
    assert failure_kwargs["error"] == StockResearchReportFailure(
        code="StockResearchScheduleDispatchError",
        message="Stock research schedule dispatch failed",
    )


@pytest.mark.asyncio
async def test_dispatcher_creates_run_report_queue_and_advances_schedule() -> None:
    queue_service = _QueueService()
    schedule = _schedule(
        next_run_at=_utc(2026, 4, 24, 1),
        schedule_type=StockResearchScheduleType.DAILY,
        hour=8,
    )
    run = _run(occurrence_at=schedule.next_run_at)
    attached_run = run.model_copy(update={"report_id": "report-1"})
    schedule_repo = SimpleNamespace(
        list_due_active_schedules=AsyncMock(return_value=[schedule]),
        advance_next_run_at=AsyncMock(return_value=schedule),
    )
    run_repo = SimpleNamespace(
        create_dispatching=AsyncMock(return_value=run),
        claim_stale_dispatching=AsyncMock(),
        claim_enqueue_failed=AsyncMock(),
        attach_report=AsyncMock(return_value=attached_run),
        mark_queued=AsyncMock(return_value=attached_run),
        mark_enqueue_failed=AsyncMock(),
    )
    report_repo = SimpleNamespace(
        create=AsyncMock(return_value=_report(schedule_run_id=run.id)),
    )
    dispatcher = StockResearchScheduleDispatcherService(
        schedule_repo=schedule_repo,
        run_repo=run_repo,
        report_repo=report_repo,
        queue_service=queue_service,
    )

    result = await dispatcher.dispatch_due(now=_utc(2026, 4, 24, 1), limit=10)

    assert result.scanned == 1
    assert result.dispatched == 1
    assert result.skipped == 0
    assert result.enqueue_failed == 0
    report_repo.create.assert_awaited_once()
    run_repo.mark_queued.assert_awaited_once_with(
        run_id=run.id,
        report_id="report-1",
    )
    schedule_repo.advance_next_run_at.assert_awaited_once()
    assert schedule_repo.advance_next_run_at.await_args.kwargs["next_run_at"] == _utc(
        2026,
        4,
        25,
        1,
    )


@pytest.mark.asyncio
async def test_dispatcher_skips_duplicate_non_stale_occurrence() -> None:
    schedule = _schedule()
    schedule_repo = SimpleNamespace(
        list_due_active_schedules=AsyncMock(return_value=[schedule]),
        advance_next_run_at=AsyncMock(),
    )
    run_repo = SimpleNamespace(
        create_dispatching=AsyncMock(return_value=None),
        claim_stale_dispatching=AsyncMock(return_value=None),
        claim_enqueue_failed=AsyncMock(return_value=None),
    )
    dispatcher = StockResearchScheduleDispatcherService(
        schedule_repo=schedule_repo,
        run_repo=run_repo,
        report_repo=SimpleNamespace(create=AsyncMock()),
        queue_service=_QueueService(),
    )

    result = await dispatcher.dispatch_due(now=_utc(), limit=10)

    assert result.scanned == 1
    assert result.dispatched == 0
    assert result.skipped == 1
    schedule_repo.advance_next_run_at.assert_not_awaited()
