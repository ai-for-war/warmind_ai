"""Dispatcher service for due stock research schedule occurrences."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.domain.models.stock_research_report import StockResearchReportTriggerType
from app.domain.models.stock_research_schedule import StockResearchSchedule
from app.repo.stock_research_report_repo import StockResearchReportRepository
from app.repo.stock_research_schedule_repo import StockResearchScheduleRepository
from app.repo.stock_research_schedule_run_repo import (
    StockResearchScheduleRunRepository,
)
from app.services.stocks.stock_research_schedule_calculator import (
    calculate_next_stock_research_run_at,
)
from app.services.stocks.stock_research_queue_service import StockResearchQueueService

SCHEDULE_DISPATCH_LOCK_SECONDS = 600


@dataclass(frozen=True)
class StockResearchScheduleDispatchResult:
    """Summary of one dispatcher pass."""

    scanned: int
    dispatched: int
    skipped: int
    enqueue_failed: int


class StockResearchScheduleDispatcherService:
    """Dispatch due stock research schedules into report worker tasks."""

    def __init__(
        self,
        *,
        schedule_repo: StockResearchScheduleRepository,
        run_repo: StockResearchScheduleRunRepository,
        report_repo: StockResearchReportRepository,
        queue_service: StockResearchQueueService,
        lock_seconds: int = SCHEDULE_DISPATCH_LOCK_SECONDS,
    ) -> None:
        self.schedule_repo = schedule_repo
        self.run_repo = run_repo
        self.report_repo = report_repo
        self.queue_service = queue_service
        self.lock_seconds = lock_seconds

    async def dispatch_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> StockResearchScheduleDispatchResult:
        """Dispatch one bounded batch of due active schedules."""
        dispatch_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        schedules = await self.schedule_repo.list_due_active_schedules(
            due_at=dispatch_now,
            limit=limit,
        )
        dispatched = 0
        skipped = 0
        enqueue_failed = 0

        for schedule in schedules:
            did_dispatch, enqueue_succeeded = await self._dispatch_schedule(
                schedule=schedule,
                now=dispatch_now,
            )
            if did_dispatch and enqueue_succeeded:
                dispatched += 1
                continue
            if did_dispatch and not enqueue_succeeded:
                enqueue_failed += 1
                continue
            skipped += 1

        return StockResearchScheduleDispatchResult(
            scanned=len(schedules),
            dispatched=dispatched,
            skipped=skipped,
            enqueue_failed=enqueue_failed,
        )

    async def _dispatch_schedule(
        self,
        *,
        schedule: StockResearchSchedule,
        now: datetime,
    ) -> tuple[bool, bool]:
        if schedule.id is None:
            return False, False

        occurrence_at = schedule.next_run_at
        lock_expires_at = now + timedelta(seconds=self.lock_seconds)
        run = await self.run_repo.create_dispatching(
            schedule_id=schedule.id,
            occurrence_at=occurrence_at,
            lock_expires_at=lock_expires_at,
        )
        if run is None:
            run = await self.run_repo.claim_stale_dispatching(
                schedule_id=schedule.id,
                occurrence_at=occurrence_at,
                now=now,
                lock_expires_at=lock_expires_at,
            )
        if run is None:
            run = await self.run_repo.claim_enqueue_failed(
                schedule_id=schedule.id,
                occurrence_at=occurrence_at,
                lock_expires_at=lock_expires_at,
            )
        if run is None or run.id is None:
            return False, False

        report_id = run.report_id
        if report_id is None:
            report = await self.report_repo.create(
                user_id=schedule.user_id,
                organization_id=schedule.organization_id,
                symbol=schedule.symbol,
                trigger_type=StockResearchReportTriggerType.SCHEDULED,
                schedule_id=schedule.id,
                schedule_run_id=run.id,
                runtime_config=schedule.runtime_config,
            )
            report_id = report.id
            attached = await self.run_repo.attach_report(
                run_id=run.id,
                report_id=report_id,
            )
            if attached is not None:
                run = attached

        enqueue_succeeded = await self.queue_service.enqueue_report(
            report_id=report_id,
            symbol=schedule.symbol,
            runtime_config=schedule.runtime_config,
        )
        if not enqueue_succeeded:
            await self.run_repo.mark_enqueue_failed(
                run_id=run.id,
                report_id=report_id,
            )
            return True, False

        await self.run_repo.mark_queued(run_id=run.id, report_id=report_id)
        await self.schedule_repo.advance_next_run_at(
            schedule_id=schedule.id,
            expected_next_run_at=occurrence_at,
            next_run_at=self._calculate_next_run_after_schedule(schedule),
        )
        return True, True

    @staticmethod
    def _calculate_next_run_after_schedule(
        schedule: StockResearchSchedule,
    ) -> datetime:
        return calculate_next_stock_research_run_at(
            schedule_type=schedule.schedule_type,
            hour=schedule.hour,
            weekdays=schedule.weekdays,
            after=schedule.next_run_at,
        )
