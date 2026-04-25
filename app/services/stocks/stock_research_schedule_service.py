"""Service layer for stock research schedule management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agents.implementations.stock_research_agent.runtime import (
    StockResearchAgentRuntimeConfig,
    resolve_stock_research_runtime_config,
)
from app.common.exceptions import (
    StockResearchScheduleDispatchError,
    StockResearchScheduleNotFoundError,
    StockSymbolNotFoundError,
)
from app.domain.models.stock_research_report import (
    StockResearchReport,
    StockResearchReportRuntimeConfig,
    StockResearchReportTriggerType,
)
from app.domain.models.stock_research_schedule import (
    StockResearchSchedule,
    StockResearchScheduleStatus,
)
from app.domain.models.user import User
from app.domain.schemas.stock_research_report import (
    StockResearchReportCreateResponse,
    StockResearchReportRuntimeConfigResponse,
)
from app.domain.schemas.stock_research_schedule import (
    StockResearchScheduleCreateRequest,
    StockResearchScheduleDefinitionRequest,
    StockResearchScheduleDefinitionResponse,
    StockResearchScheduleDeleteResponse,
    StockResearchScheduleListResponse,
    StockResearchScheduleResponse,
    StockResearchScheduleSummary,
    StockResearchScheduleUpdateRequest,
)
from app.repo.stock_research_report_repo import StockResearchReportRepository
from app.repo.stock_research_schedule_repo import StockResearchScheduleRepository
from app.repo.stock_symbol_repo import StockSymbolRepository
from app.services.stocks.stock_research_schedule_calculator import (
    calculate_next_stock_research_run_at,
)
from app.services.stocks.stock_research_queue_service import (
    StockResearchQueueService,
)


class StockResearchScheduleService:
    """Coordinate stock research schedule CRUD and immediate schedule runs."""

    def __init__(
        self,
        *,
        schedule_repo: StockResearchScheduleRepository,
        report_repo: StockResearchReportRepository,
        stock_repo: StockSymbolRepository,
        queue_service: StockResearchQueueService | None = None,
    ) -> None:
        self.schedule_repo = schedule_repo
        self.report_repo = report_repo
        self.stock_repo = stock_repo
        self.queue_service = queue_service

    async def create_schedule(
        self,
        *,
        current_user: User,
        organization_id: str,
        request: StockResearchScheduleCreateRequest,
    ) -> StockResearchScheduleResponse:
        """Validate and create one recurring stock research schedule."""
        symbol = request.symbol.strip().upper()
        await self._ensure_symbol_exists(symbol)
        runtime_config = self._resolve_runtime_config(request.runtime_config)
        next_run_at = self._calculate_next_run_at(request.schedule)

        schedule = await self.schedule_repo.create(
            user_id=current_user.id,
            organization_id=organization_id,
            symbol=symbol,
            runtime_config=self._to_runtime_config_model(runtime_config),
            schedule_type=request.schedule.schedule_type,
            hour=request.schedule.hour,
            weekdays=request.schedule.weekdays,
            next_run_at=next_run_at,
        )
        return self._to_schedule_response(schedule)

    async def list_schedules(
        self,
        *,
        current_user: User,
        organization_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> StockResearchScheduleListResponse:
        """List one caller's non-deleted schedules in an organization."""
        schedules, total = await self.schedule_repo.list_by_user_and_organization(
            user_id=current_user.id,
            organization_id=organization_id,
            page=page,
            page_size=page_size,
        )
        return StockResearchScheduleListResponse(
            items=[self._to_schedule_summary(schedule) for schedule in schedules],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_schedule(
        self,
        *,
        current_user: User,
        organization_id: str,
        schedule_id: str,
    ) -> StockResearchScheduleResponse:
        """Read one caller-owned stock research schedule."""
        schedule = await self._get_owned_schedule(
            current_user=current_user,
            organization_id=organization_id,
            schedule_id=schedule_id,
        )
        return self._to_schedule_response(schedule)

    async def update_schedule(
        self,
        *,
        current_user: User,
        organization_id: str,
        schedule_id: str,
        request: StockResearchScheduleUpdateRequest,
    ) -> StockResearchScheduleResponse:
        """Update one caller-owned non-deleted stock research schedule."""
        existing = await self._get_owned_schedule(
            current_user=current_user,
            organization_id=organization_id,
            schedule_id=schedule_id,
        )

        symbol = request.symbol
        if symbol is not None:
            await self._ensure_symbol_exists(symbol)

        runtime_config = (
            None
            if request.runtime_config is None
            else self._to_runtime_config_model(
                self._resolve_runtime_config(request.runtime_config)
            )
        )
        schedule_definition = request.schedule
        effective_definition = (
            schedule_definition
            or StockResearchScheduleDefinitionRequest(
                type=existing.schedule_type,
                hour=existing.hour,
                weekdays=existing.weekdays,
            )
        )
        next_run_at = (
            self._calculate_next_run_at(effective_definition)
            if schedule_definition is not None
            or request.status == StockResearchScheduleStatus.ACTIVE
            else None
        )

        update_kwargs: dict[str, Any] = {}
        if symbol is not None:
            update_kwargs["symbol"] = symbol
        if runtime_config is not None:
            update_kwargs["runtime_config"] = runtime_config
        if schedule_definition is not None:
            update_kwargs.update(
                {
                    "schedule_type": schedule_definition.schedule_type,
                    "hour": schedule_definition.hour,
                    "weekdays": schedule_definition.weekdays,
                }
            )
        if request.status is not None:
            update_kwargs["status"] = request.status
        if next_run_at is not None:
            update_kwargs["next_run_at"] = next_run_at

        updated = await self.schedule_repo.update_owned_schedule(
            schedule_id=existing.id,
            user_id=current_user.id,
            organization_id=organization_id,
            **update_kwargs,
        )
        if updated is None:
            raise StockResearchScheduleNotFoundError()
        return self._to_schedule_response(updated)

    async def pause_schedule(
        self,
        *,
        current_user: User,
        organization_id: str,
        schedule_id: str,
    ) -> StockResearchScheduleResponse:
        """Pause one caller-owned stock research schedule."""
        return await self.update_schedule(
            current_user=current_user,
            organization_id=organization_id,
            schedule_id=schedule_id,
            request=StockResearchScheduleUpdateRequest(
                status=StockResearchScheduleStatus.PAUSED
            ),
        )

    async def resume_schedule(
        self,
        *,
        current_user: User,
        organization_id: str,
        schedule_id: str,
    ) -> StockResearchScheduleResponse:
        """Resume one caller-owned stock research schedule from now."""
        return await self.update_schedule(
            current_user=current_user,
            organization_id=organization_id,
            schedule_id=schedule_id,
            request=StockResearchScheduleUpdateRequest(
                status=StockResearchScheduleStatus.ACTIVE
            ),
        )

    async def delete_schedule(
        self,
        *,
        current_user: User,
        organization_id: str,
        schedule_id: str,
    ) -> StockResearchScheduleDeleteResponse:
        """Soft-delete one caller-owned stock research schedule."""
        schedule = await self._get_owned_schedule(
            current_user=current_user,
            organization_id=organization_id,
            schedule_id=schedule_id,
        )
        deleted = await self.schedule_repo.soft_delete_owned_schedule(
            schedule_id=schedule.id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        if deleted is None:
            raise StockResearchScheduleNotFoundError()
        return StockResearchScheduleDeleteResponse(id=schedule.id, deleted=True)

    async def run_now(
        self,
        *,
        current_user: User,
        organization_id: str,
        schedule_id: str,
    ) -> StockResearchReportCreateResponse:
        """Create one immediate report from a schedule without moving next_run_at."""
        schedule = await self._get_owned_schedule(
            current_user=current_user,
            organization_id=organization_id,
            schedule_id=schedule_id,
        )
        report = await self._create_report_from_schedule(
            schedule=schedule,
            schedule_run_id=None,
        )
        if not await self._enqueue_report(report=report):
            raise StockResearchScheduleDispatchError()
        return self._to_report_create_response(report)

    async def _get_owned_schedule(
        self,
        *,
        current_user: User,
        organization_id: str,
        schedule_id: str,
    ) -> StockResearchSchedule:
        schedule = await self.schedule_repo.find_owned_schedule(
            schedule_id=schedule_id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        if schedule is None:
            raise StockResearchScheduleNotFoundError()
        return schedule

    async def _ensure_symbol_exists(self, symbol: str) -> None:
        if not await self.stock_repo.exists_by_symbol(symbol):
            raise StockSymbolNotFoundError()

    async def _create_report_from_schedule(
        self,
        *,
        schedule: StockResearchSchedule,
        schedule_run_id: str | None,
    ) -> StockResearchReport:
        return await self.report_repo.create(
            user_id=schedule.user_id,
            organization_id=schedule.organization_id,
            symbol=schedule.symbol,
            trigger_type=StockResearchReportTriggerType.SCHEDULED,
            schedule_id=schedule.id,
            schedule_run_id=schedule_run_id,
            runtime_config=schedule.runtime_config,
        )

    async def _enqueue_report(self, *, report: StockResearchReport) -> bool:
        if self.queue_service is None:
            raise StockResearchScheduleDispatchError()
        return await self.queue_service.enqueue_report_model(report)

    @staticmethod
    def _resolve_runtime_config(request: Any) -> StockResearchAgentRuntimeConfig:
        return resolve_stock_research_runtime_config(
            provider=request.provider,
            model=request.model,
            reasoning=request.reasoning,
        )

    @staticmethod
    def _to_runtime_config_model(
        runtime_config: StockResearchAgentRuntimeConfig,
    ) -> StockResearchReportRuntimeConfig:
        return StockResearchReportRuntimeConfig(
            provider=runtime_config.provider,
            model=runtime_config.model,
            reasoning=runtime_config.reasoning,
        )

    @staticmethod
    def _calculate_next_run_at(
        definition: StockResearchScheduleDefinitionRequest,
        *,
        after: datetime | None = None,
    ) -> datetime:
        return calculate_next_stock_research_run_at(
            schedule_type=definition.schedule_type,
            hour=definition.hour,
            weekdays=definition.weekdays,
            after=after or datetime.now(timezone.utc),
        )

    @classmethod
    def _to_schedule_response(
        cls,
        schedule: StockResearchSchedule,
    ) -> StockResearchScheduleResponse:
        summary = cls._to_schedule_summary(schedule)
        return StockResearchScheduleResponse(**summary.model_dump())

    @staticmethod
    def _to_schedule_summary(
        schedule: StockResearchSchedule,
    ) -> StockResearchScheduleSummary:
        return StockResearchScheduleSummary(
            id=schedule.id,
            symbol=schedule.symbol,
            status=schedule.status,
            schedule=StockResearchScheduleDefinitionResponse(
                type=schedule.schedule_type,
                hour=schedule.hour,
                weekdays=schedule.weekdays,
            ),
            next_run_at=schedule.next_run_at,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at,
            runtime_config=StockResearchReportRuntimeConfigResponse(
                provider=schedule.runtime_config.provider,
                model=schedule.runtime_config.model,
                reasoning=schedule.runtime_config.reasoning,
            ),
        )

    @staticmethod
    def _to_report_create_response(
        report: StockResearchReport,
    ) -> StockResearchReportCreateResponse:
        return StockResearchReportCreateResponse(
            id=report.id,
            symbol=report.symbol,
            status=report.status,
            created_at=report.created_at,
            started_at=report.started_at,
            completed_at=report.completed_at,
            updated_at=report.updated_at,
            runtime_config=(
                None
                if report.runtime_config is None
                else StockResearchReportRuntimeConfigResponse(
                    provider=report.runtime_config.provider,
                    model=report.runtime_config.model,
                    reasoning=report.runtime_config.reasoning,
                )
            ),
        )
