from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.domain.models.stock_research_report import (
    StockResearchReport,
    StockResearchReportRuntimeConfig,
    StockResearchReportStatus,
    StockResearchReportTriggerType,
)
from app.domain.models.stock_research_schedule import (
    StockResearchSchedule,
    StockResearchScheduleRun,
    StockResearchScheduleRunStatus,
    StockResearchScheduleStatus,
    StockResearchScheduleType,
)
from app.services.stocks.stock_research_schedule_dispatcher_service import (
    StockResearchScheduleDispatcherService,
)


def _utc(
    year: int = 2026,
    month: int = 4,
    day: int = 24,
    hour: int = 1,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _runtime_config() -> StockResearchReportRuntimeConfig:
    return StockResearchReportRuntimeConfig(
        provider="openai",
        model="gpt-5.2",
        reasoning="high",
    )


def _schedule(
    *,
    schedule_id: str = "schedule-1",
    schedule_type: StockResearchScheduleType = StockResearchScheduleType.DAILY,
    hour: int | None = 8,
    next_run_at: datetime | None = None,
) -> StockResearchSchedule:
    return StockResearchSchedule(
        _id=schedule_id,
        user_id="user-1",
        organization_id="org-1",
        symbol="FPT",
        runtime_config=_runtime_config(),
        schedule_type=schedule_type,
        hour=hour,
        weekdays=[],
        status=StockResearchScheduleStatus.ACTIVE,
        next_run_at=next_run_at or _utc(2026, 4, 24, 1),
        created_at=_utc(2026, 4, 23, 1),
        updated_at=_utc(2026, 4, 23, 1),
    )


class _StatefulScheduleRepo:
    def __init__(
        self,
        schedules: list[StockResearchSchedule],
        *,
        advance: bool = True,
    ) -> None:
        self.schedules = {schedule.id: schedule for schedule in schedules}
        self.advance = advance
        self.advance_calls: list[dict[str, object]] = []

    async def list_due_active_schedules(
        self,
        *,
        due_at: datetime,
        limit: int = 100,
    ) -> list[StockResearchSchedule]:
        due = [
            schedule
            for schedule in self.schedules.values()
            if schedule.status == StockResearchScheduleStatus.ACTIVE
            and schedule.next_run_at <= due_at
        ]
        return sorted(due, key=lambda schedule: schedule.next_run_at)[:limit]

    async def advance_next_run_at(
        self,
        *,
        schedule_id: str,
        expected_next_run_at: datetime,
        next_run_at: datetime,
    ) -> StockResearchSchedule | None:
        self.advance_calls.append(
            {
                "schedule_id": schedule_id,
                "expected_next_run_at": expected_next_run_at,
                "next_run_at": next_run_at,
            }
        )
        schedule = self.schedules.get(schedule_id)
        if schedule is None or schedule.next_run_at != expected_next_run_at:
            return None
        if not self.advance:
            return schedule

        updated = schedule.model_copy(update={"next_run_at": next_run_at})
        self.schedules[schedule_id] = updated
        return updated


class _StatefulRunRepo:
    def __init__(self) -> None:
        self.runs_by_key: dict[tuple[str, datetime], StockResearchScheduleRun] = {}
        self.runs_by_id: dict[str, StockResearchScheduleRun] = {}
        self.create_calls = 0
        self.claim_stale_calls = 0
        self.mark_enqueue_failed_calls = 0
        self._lock = asyncio.Lock()

    async def create_dispatching(
        self,
        *,
        schedule_id: str,
        occurrence_at: datetime,
        lock_expires_at: datetime,
    ) -> StockResearchScheduleRun | None:
        async with self._lock:
            self.create_calls += 1
            key = (schedule_id, occurrence_at)
            if key in self.runs_by_key:
                return None

            run = StockResearchScheduleRun(
                _id=f"6807dd18c5d8d14d4af1d{len(self.runs_by_id) + 111:03d}",
                schedule_id=schedule_id,
                occurrence_at=occurrence_at,
                status=StockResearchScheduleRunStatus.DISPATCHING,
                report_id=None,
                lock_expires_at=lock_expires_at,
                created_at=_utc(),
                updated_at=_utc(),
            )
            self.runs_by_key[key] = run
            self.runs_by_id[run.id] = run
            return run

    async def claim_stale_dispatching(
        self,
        *,
        schedule_id: str,
        occurrence_at: datetime,
        now: datetime,
        lock_expires_at: datetime,
    ) -> StockResearchScheduleRun | None:
        self.claim_stale_calls += 1
        run = self.runs_by_key.get((schedule_id, occurrence_at))
        if (
            run is None
            or run.status != StockResearchScheduleRunStatus.DISPATCHING
            or run.lock_expires_at is None
            or run.lock_expires_at > now
        ):
            return None

        updated = run.model_copy(update={"lock_expires_at": lock_expires_at})
        self.runs_by_key[(schedule_id, occurrence_at)] = updated
        self.runs_by_id[updated.id] = updated
        return updated

    async def attach_report(
        self,
        *,
        run_id: str,
        report_id: str,
    ) -> StockResearchScheduleRun | None:
        run = self.runs_by_id.get(run_id)
        if (
            run is None
            or run.status != StockResearchScheduleRunStatus.DISPATCHING
            or run.report_id is not None
        ):
            return None

        updated = run.model_copy(update={"report_id": report_id})
        self._save(updated)
        return updated

    async def mark_queued(
        self,
        *,
        run_id: str,
        report_id: str,
    ) -> StockResearchScheduleRun | None:
        return self._mark_terminal(
            run_id=run_id,
            report_id=report_id,
            status=StockResearchScheduleRunStatus.QUEUED,
        )

    async def mark_enqueue_failed(
        self,
        *,
        run_id: str,
        report_id: str | None = None,
    ) -> StockResearchScheduleRun | None:
        self.mark_enqueue_failed_calls += 1
        return self._mark_terminal(
            run_id=run_id,
            report_id=report_id,
            status=StockResearchScheduleRunStatus.ENQUEUE_FAILED,
        )

    def _mark_terminal(
        self,
        *,
        run_id: str,
        report_id: str | None,
        status: StockResearchScheduleRunStatus,
    ) -> StockResearchScheduleRun | None:
        run = self.runs_by_id.get(run_id)
        if run is None or run.status != StockResearchScheduleRunStatus.DISPATCHING:
            return None

        updated = run.model_copy(
            update={
                "status": status,
                "report_id": report_id or run.report_id,
            }
        )
        self._save(updated)
        return updated

    def _save(self, run: StockResearchScheduleRun) -> None:
        self.runs_by_key[(run.schedule_id, run.occurrence_at)] = run
        self.runs_by_id[run.id] = run


class _StatefulReportRepo:
    def __init__(self) -> None:
        self.reports: list[StockResearchReport] = []

    async def create(self, **kwargs) -> StockResearchReport:
        report = StockResearchReport(
            _id=f"report-{len(self.reports) + 1}",
            user_id=kwargs["user_id"],
            organization_id=kwargs["organization_id"],
            symbol=kwargs["symbol"],
            status=StockResearchReportStatus.QUEUED,
            trigger_type=kwargs.get(
                "trigger_type",
                StockResearchReportTriggerType.SCHEDULED,
            ),
            schedule_id=kwargs.get("schedule_id"),
            schedule_run_id=kwargs.get("schedule_run_id"),
            runtime_config=kwargs.get("runtime_config"),
            created_at=_utc(),
            updated_at=_utc(),
        )
        self.reports.append(report)
        return report


class _QueueService:
    def __init__(self, *, success: bool = True) -> None:
        self.success = success
        self.calls: list[dict[str, object]] = []

    async def enqueue_report(self, **kwargs) -> bool:
        self.calls.append(kwargs)
        return self.success


def _dispatcher(
    *,
    schedule_repo: _StatefulScheduleRepo,
    run_repo: _StatefulRunRepo,
    report_repo: _StatefulReportRepo | None = None,
    queue_service: _QueueService | None = None,
) -> StockResearchScheduleDispatcherService:
    return StockResearchScheduleDispatcherService(
        schedule_repo=schedule_repo,
        run_repo=run_repo,
        report_repo=report_repo or _StatefulReportRepo(),
        queue_service=queue_service or _QueueService(),
    )


@pytest.mark.asyncio
async def test_repeated_dispatcher_calls_for_same_occurrence_create_one_report() -> None:
    schedule = _schedule(next_run_at=_utc(2026, 4, 24, 1))
    schedule_repo = _StatefulScheduleRepo([schedule], advance=False)
    run_repo = _StatefulRunRepo()
    report_repo = _StatefulReportRepo()
    queue_service = _QueueService()
    dispatcher = _dispatcher(
        schedule_repo=schedule_repo,
        run_repo=run_repo,
        report_repo=report_repo,
        queue_service=queue_service,
    )

    first = await dispatcher.dispatch_due(now=_utc(2026, 4, 24, 1))
    second = await dispatcher.dispatch_due(now=_utc(2026, 4, 24, 1))

    assert first.dispatched == 1
    assert second.dispatched == 0
    assert second.skipped == 1
    assert len(report_repo.reports) == 1
    assert len(run_repo.runs_by_key) == 1
    assert len(queue_service.calls) == 1


@pytest.mark.asyncio
async def test_concurrent_claims_for_same_occurrence_resolve_to_single_run() -> None:
    run_repo = _StatefulRunRepo()
    occurrence_at = _utc(2026, 4, 24, 1)

    results = await asyncio.gather(
        *[
            run_repo.create_dispatching(
                schedule_id="schedule-1",
                occurrence_at=occurrence_at,
                lock_expires_at=_utc(2026, 4, 24, 1, 10),
            )
            for _ in range(5)
        ]
    )

    created_runs = [run for run in results if run is not None]
    assert len(created_runs) == 1
    assert len(run_repo.runs_by_key) == 1
    assert run_repo.create_calls == 5


@pytest.mark.asyncio
async def test_later_due_occurrence_can_dispatch_while_previous_report_is_running() -> None:
    schedule = _schedule(
        schedule_type=StockResearchScheduleType.EVERY_15_MINUTES,
        hour=None,
        next_run_at=_utc(2026, 4, 24, 1),
    )
    schedule_repo = _StatefulScheduleRepo([schedule])
    run_repo = _StatefulRunRepo()
    report_repo = _StatefulReportRepo()
    dispatcher = _dispatcher(
        schedule_repo=schedule_repo,
        run_repo=run_repo,
        report_repo=report_repo,
    )

    first = await dispatcher.dispatch_due(now=_utc(2026, 4, 24, 1))
    second = await dispatcher.dispatch_due(now=_utc(2026, 4, 24, 1, 15))

    assert first.dispatched == 1
    assert second.dispatched == 1
    assert [report.schedule_run_id for report in report_repo.reports] == [
        "6807dd18c5d8d14d4af1d111",
        "6807dd18c5d8d14d4af1d112",
    ]
    assert [run.occurrence_at for run in run_repo.runs_by_key.values()] == [
        _utc(2026, 4, 24, 1),
        _utc(2026, 4, 24, 1, 15),
    ]


@pytest.mark.asyncio
async def test_stale_dispatching_run_with_report_is_recovered_and_queued() -> None:
    occurrence_at = _utc(2026, 4, 24, 1)
    schedule = _schedule(next_run_at=occurrence_at)
    schedule_repo = _StatefulScheduleRepo([schedule])
    run_repo = _StatefulRunRepo()
    stale_run = StockResearchScheduleRun(
        _id="6807dd18c5d8d14d4af1d111",
        schedule_id="schedule-1",
        occurrence_at=occurrence_at,
        status=StockResearchScheduleRunStatus.DISPATCHING,
        report_id="report-existing",
        lock_expires_at=_utc(2026, 4, 24, 0, 50),
        created_at=_utc(),
        updated_at=_utc(),
    )
    run_repo._save(stale_run)
    report_repo = _StatefulReportRepo()
    queue_service = _QueueService()
    dispatcher = _dispatcher(
        schedule_repo=schedule_repo,
        run_repo=run_repo,
        report_repo=report_repo,
        queue_service=queue_service,
    )

    result = await dispatcher.dispatch_due(now=_utc(2026, 4, 24, 1))

    assert result.dispatched == 1
    assert run_repo.claim_stale_calls == 1
    assert report_repo.reports == []
    assert queue_service.calls[0]["report_id"] == "report-existing"
    assert (
        run_repo.runs_by_id[stale_run.id].status
        == StockResearchScheduleRunStatus.QUEUED
    )


@pytest.mark.asyncio
async def test_enqueue_failure_is_recorded_without_advancing_schedule() -> None:
    schedule = _schedule(next_run_at=_utc(2026, 4, 24, 1))
    schedule_repo = _StatefulScheduleRepo([schedule])
    run_repo = _StatefulRunRepo()
    report_repo = _StatefulReportRepo()
    dispatcher = _dispatcher(
        schedule_repo=schedule_repo,
        run_repo=run_repo,
        report_repo=report_repo,
        queue_service=_QueueService(success=False),
    )

    result = await dispatcher.dispatch_due(now=_utc(2026, 4, 24, 1))

    assert result.dispatched == 0
    assert result.enqueue_failed == 1
    assert len(report_repo.reports) == 1
    assert run_repo.mark_enqueue_failed_calls == 1
    assert (
        next(iter(run_repo.runs_by_key.values())).status
        == StockResearchScheduleRunStatus.ENQUEUE_FAILED
    )
    assert schedule_repo.schedules["schedule-1"].next_run_at == _utc(2026, 4, 24, 1)
