"""Stock research report API router."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.agents.implementations.stock_research_agent.runtime import (
    get_default_stock_research_runtime_config,
    get_stock_research_runtime_catalog,
)
from app.common.service import get_stock_research_service
from app.domain.models.user import User
from app.domain.schemas.stock_research_report import (
    MAX_STOCK_RESEARCH_SYMBOL_LENGTH,
    StockResearchCatalogModelResponse,
    StockResearchCatalogProviderResponse,
    StockResearchCatalogResponse,
    StockResearchReportCreateRequest,
    StockResearchReportCreateResponse,
    StockResearchReportListResponse,
    StockResearchReportResponse,
)
from app.services.stocks.stock_research_service import StockResearchService

router = APIRouter(prefix="/stock-research/reports", tags=["stock-research"])


@router.get("/catalog", response_model=StockResearchCatalogResponse)
async def get_stock_research_catalog(
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
) -> StockResearchCatalogResponse:
    """Return the supported provider/model/reasoning catalog for stock research."""
    default_runtime = get_default_stock_research_runtime_config()
    catalog = get_stock_research_runtime_catalog()

    return StockResearchCatalogResponse(
        default_provider=default_runtime.provider,
        default_model=default_runtime.model,
        default_reasoning=default_runtime.reasoning,
        providers=[
            StockResearchCatalogProviderResponse(
                provider=provider.provider,
                display_name=provider.display_name,
                is_default=provider.is_default,
                models=[
                    StockResearchCatalogModelResponse(
                        model=model.model,
                        reasoning_options=list(model.reasoning_options),
                        default_reasoning=model.default_reasoning,
                        is_default=model.is_default,
                    )
                    for model in provider.models
                ],
            )
            for provider in catalog
        ],
    )


@router.post(
    "",
    response_model=StockResearchReportCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_stock_research_report(
    request: StockResearchReportCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchService = Depends(get_stock_research_service),
) -> StockResearchReportCreateResponse:
    """Accept one stock research report request and schedule background processing."""
    response = await service.create_report_request(
        current_user=current_user,
        organization_id=org_context.organization_id,
        request=request,
    )
    runtime_config = service.resolve_request_runtime_config(request)
    background_tasks.add_task(
        service.process_report,
        report_id=response.id,
        symbol=response.symbol,
        runtime_config=runtime_config,
    )
    return response


@router.get("/{report_id}", response_model=StockResearchReportResponse)
async def get_stock_research_report(
    report_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchService = Depends(get_stock_research_service),
) -> StockResearchReportResponse:
    """Read one caller-owned stock research report."""
    return await service.get_report(
        current_user=current_user,
        organization_id=org_context.organization_id,
        report_id=report_id,
    )


@router.get("", response_model=StockResearchReportListResponse)
async def list_stock_research_reports(
    symbol: str | None = Query(
        default=None,
        min_length=1,
        max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH,
    ),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: StockResearchService = Depends(get_stock_research_service),
) -> StockResearchReportListResponse:
    """List the current user's stock research reports in one organization."""
    return await service.list_reports(
        current_user=current_user,
        organization_id=org_context.organization_id,
        symbol=symbol,
    )
