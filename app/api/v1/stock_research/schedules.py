"""Stock research schedule API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.service import get_stock_research_schedule_service
from app.domain.models.user import User
from app.domain.schemas.stock_research_report import StockResearchReportCreateResponse
from app.domain.schemas.stock_research_schedule import (
    StockResearchScheduleCreateRequest,
    StockResearchScheduleDeleteResponse,
    StockResearchScheduleListResponse,
    StockResearchScheduleResponse,
    StockResearchScheduleUpdateRequest,
)
from app.services.stocks.stock_research_schedule_service import (
    StockResearchScheduleService,
)

router = APIRouter(prefix="/stock-research/schedules", tags=["stock-research"])


@router.post(
    "",
    response_model=StockResearchScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stock_research_schedule(
    request: StockResearchScheduleCreateRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchScheduleService = Depends(
        get_stock_research_schedule_service
    ),
) -> StockResearchScheduleResponse:
    """Create one recurring stock research schedule."""
    return await service.create_schedule(
        current_user=current_user,
        organization_id=org_context.organization_id,
        request=request,
    )


@router.get("", response_model=StockResearchScheduleListResponse)
async def list_stock_research_schedules(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchScheduleService = Depends(
        get_stock_research_schedule_service
    ),
) -> StockResearchScheduleListResponse:
    """List current user's stock research schedules in one organization."""
    return await service.list_schedules(
        current_user=current_user,
        organization_id=org_context.organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/{schedule_id}", response_model=StockResearchScheduleResponse)
async def get_stock_research_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchScheduleService = Depends(
        get_stock_research_schedule_service
    ),
) -> StockResearchScheduleResponse:
    """Read one caller-owned stock research schedule."""
    return await service.get_schedule(
        current_user=current_user,
        organization_id=org_context.organization_id,
        schedule_id=schedule_id,
    )


@router.patch("/{schedule_id}", response_model=StockResearchScheduleResponse)
async def update_stock_research_schedule(
    schedule_id: str,
    request: StockResearchScheduleUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchScheduleService = Depends(
        get_stock_research_schedule_service
    ),
) -> StockResearchScheduleResponse:
    """Update one caller-owned stock research schedule."""
    return await service.update_schedule(
        current_user=current_user,
        organization_id=org_context.organization_id,
        schedule_id=schedule_id,
        request=request,
    )


@router.post("/{schedule_id}/pause", response_model=StockResearchScheduleResponse)
async def pause_stock_research_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchScheduleService = Depends(
        get_stock_research_schedule_service
    ),
) -> StockResearchScheduleResponse:
    """Pause one caller-owned stock research schedule."""
    return await service.pause_schedule(
        current_user=current_user,
        organization_id=org_context.organization_id,
        schedule_id=schedule_id,
    )


@router.post("/{schedule_id}/resume", response_model=StockResearchScheduleResponse)
async def resume_stock_research_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchScheduleService = Depends(
        get_stock_research_schedule_service
    ),
) -> StockResearchScheduleResponse:
    """Resume one caller-owned stock research schedule."""
    return await service.resume_schedule(
        current_user=current_user,
        organization_id=org_context.organization_id,
        schedule_id=schedule_id,
    )


@router.delete("/{schedule_id}", response_model=StockResearchScheduleDeleteResponse)
async def delete_stock_research_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchScheduleService = Depends(
        get_stock_research_schedule_service
    ),
) -> StockResearchScheduleDeleteResponse:
    """Delete one caller-owned stock research schedule."""
    return await service.delete_schedule(
        current_user=current_user,
        organization_id=org_context.organization_id,
        schedule_id=schedule_id,
    )


@router.post(
    "/{schedule_id}/run-now",
    response_model=StockResearchReportCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_stock_research_schedule_now(
    schedule_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchScheduleService = Depends(
        get_stock_research_schedule_service
    ),
) -> StockResearchReportCreateResponse:
    """Create one immediate report from a schedule without moving its cadence."""
    return await service.run_now(
        current_user=current_user,
        organization_id=org_context.organization_id,
        schedule_id=schedule_id,
    )
