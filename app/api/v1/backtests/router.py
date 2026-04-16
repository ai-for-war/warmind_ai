"""Dedicated frontend-facing backtest API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
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
    ___: BacktestService = Depends(get_backtest_service),
) -> BacktestApiTemplateListResponse:
    """Return the FE-facing backtest template catalog."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Backtest template catalog endpoint is not implemented yet",
    )


@router.post("/run", response_model=BacktestApiRunResponse)
async def run_backtest(
    request: BacktestApiRunRequest,
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    ___: BacktestService = Depends(get_backtest_service),
) -> BacktestApiRunResponse:
    """Execute one synchronous FE-facing backtest run."""
    del request
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Backtest run endpoint is not implemented yet",
    )
