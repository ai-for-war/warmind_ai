"""Dedicated frontend-facing backtest API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.backtests.presenters import (
    build_run_response,
    build_template_catalog,
)
from app.common.service import get_backtest_service
from app.domain.models.user import User
from app.domain.schemas.backtest_api import (
    BacktestApiRunRequest,
    BacktestApiRunResponse,
    BacktestApiTemplateListResponse,
)
from app.services.backtest.service import BacktestService

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.get("/templates", response_model=BacktestApiTemplateListResponse)
async def list_backtest_templates(
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestApiTemplateListResponse:
    """Return the FE-facing backtest template catalog."""
    return build_template_catalog(service)


@router.post("/run", response_model=BacktestApiRunResponse)
async def run_backtest(
    request: BacktestApiRunRequest,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    service: BacktestService = Depends(get_backtest_service),
) -> BacktestApiRunResponse:
    """Execute one synchronous FE-facing backtest run."""
    internal_request = request.to_internal_request()
    result = await service.run_backtest(internal_request)
    return build_run_response(internal_request, result)
