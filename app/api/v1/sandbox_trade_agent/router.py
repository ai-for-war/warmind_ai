"""Sandbox trade-agent session and history API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.service import get_sandbox_trade_agent_session_service
from app.domain.models.user import User
from app.domain.schemas.sandbox_trade_agent import (
    SandboxTradeOrderListResponse,
    SandboxTradePortfolioSnapshotListResponse,
    SandboxTradePortfolioStateResponse,
    SandboxTradeSessionCreateRequest,
    SandboxTradeSessionDeleteResponse,
    SandboxTradeSessionLifecycleResponse,
    SandboxTradeSessionListResponse,
    SandboxTradeSessionResponse,
    SandboxTradeSessionUpdateRequest,
    SandboxTradeSettlementListResponse,
    SandboxTradeTickListResponse,
)
from app.services.stocks.sandbox_trade_agent_service import (
    SandboxTradeAgentSessionService,
)

router = APIRouter(
    prefix="/sandbox-trade-agent/sessions",
    tags=["sandbox-trade-agent"],
)


@router.post(
    "",
    response_model=SandboxTradeSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sandbox_trade_session(
    request: SandboxTradeSessionCreateRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeSessionResponse:
    """Create one autonomous sandbox trade-agent session."""
    return await service.create_session(
        current_user=current_user,
        organization_id=org_context.organization_id,
        request=request,
    )


@router.get("", response_model=SandboxTradeSessionListResponse)
async def list_sandbox_trade_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeSessionListResponse:
    """List the current user's sandbox trade-agent sessions."""
    return await service.list_sessions(
        current_user=current_user,
        organization_id=org_context.organization_id,
        page=page,
        page_size=page_size,
    )


@router.get("/{session_id}", response_model=SandboxTradeSessionResponse)
async def get_sandbox_trade_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeSessionResponse:
    """Read one caller-owned sandbox trade-agent session."""
    return await service.get_session(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
    )


@router.patch("/{session_id}", response_model=SandboxTradeSessionResponse)
async def update_sandbox_trade_session(
    session_id: str,
    request: SandboxTradeSessionUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeSessionResponse:
    """Update mutable fields on one sandbox trade-agent session."""
    return await service.update_session(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
        request=request,
    )


@router.post(
    "/{session_id}/pause",
    response_model=SandboxTradeSessionLifecycleResponse,
)
async def pause_sandbox_trade_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeSessionLifecycleResponse:
    """Pause one active sandbox trade-agent session."""
    return await service.pause_session(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
    )


@router.post(
    "/{session_id}/resume",
    response_model=SandboxTradeSessionLifecycleResponse,
)
async def resume_sandbox_trade_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeSessionLifecycleResponse:
    """Resume one paused sandbox trade-agent session."""
    return await service.resume_session(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
    )


@router.post(
    "/{session_id}/stop",
    response_model=SandboxTradeSessionLifecycleResponse,
)
async def stop_sandbox_trade_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeSessionLifecycleResponse:
    """Stop one sandbox trade-agent session permanently."""
    return await service.stop_session(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
    )


@router.delete("/{session_id}", response_model=SandboxTradeSessionDeleteResponse)
async def delete_sandbox_trade_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeSessionDeleteResponse:
    """Soft-delete one caller-owned sandbox trade-agent session."""
    return await service.delete_session(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
    )


@router.get("/{session_id}/ticks", response_model=SandboxTradeTickListResponse)
async def list_sandbox_trade_ticks(
    session_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeTickListResponse:
    """List tick history for one sandbox trade-agent session."""
    return await service.list_ticks(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
        page=page,
        page_size=page_size,
    )


@router.get("/{session_id}/orders", response_model=SandboxTradeOrderListResponse)
async def list_sandbox_trade_orders(
    session_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeOrderListResponse:
    """List sandbox order history for one session."""
    return await service.list_orders(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{session_id}/settlements",
    response_model=SandboxTradeSettlementListResponse,
)
async def list_sandbox_trade_settlements(
    session_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradeSettlementListResponse:
    """List settlement ledger history for one session."""
    return await service.list_settlements(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{session_id}/portfolio",
    response_model=SandboxTradePortfolioStateResponse,
)
async def get_sandbox_trade_portfolio_state(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradePortfolioStateResponse:
    """Read current position, latest snapshot, and pending settlements."""
    return await service.get_portfolio_state(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
    )


@router.get(
    "/{session_id}/portfolio/snapshots",
    response_model=SandboxTradePortfolioSnapshotListResponse,
)
async def list_sandbox_trade_portfolio_snapshots(
    session_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    service: SandboxTradeAgentSessionService = Depends(
        get_sandbox_trade_agent_session_service
    ),
) -> SandboxTradePortfolioSnapshotListResponse:
    """List portfolio accounting snapshots for one session."""
    return await service.list_portfolio_snapshots(
        current_user=current_user,
        organization_id=org_context.organization_id,
        session_id=session_id,
        page=page,
        page_size=page_size,
    )
