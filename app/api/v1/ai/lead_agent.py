"""Lead-agent API endpoints for thread creation and execution."""

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.service import get_lead_agent_service
from app.domain.models.user import User
from app.domain.schemas.lead_agent import (
    CreateLeadAgentThreadRequest,
    CreateLeadAgentThreadResponse,
    LeadAgentThreadRunRequest,
    LeadAgentThreadRunResponse,
)
from app.services.ai.lead_agent_service import LeadAgentService

router = APIRouter(prefix="/lead-agent", tags=["lead-agent"])


@router.post(
    "/threads",
    response_model=CreateLeadAgentThreadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread(
    _request: CreateLeadAgentThreadRequest | None = None,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_service: LeadAgentService = Depends(get_lead_agent_service),
) -> CreateLeadAgentThreadResponse:
    """Create a new lead-agent thread scoped to the authenticated caller."""
    thread_id = await lead_agent_service.create_thread(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
    )
    return CreateLeadAgentThreadResponse(thread_id=thread_id)


@router.post(
    "/threads/{thread_id}/runs",
    response_model=LeadAgentThreadRunResponse,
)
async def run_thread(
    thread_id: str,
    request: LeadAgentThreadRunRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_service: LeadAgentService = Depends(get_lead_agent_service),
) -> LeadAgentThreadRunResponse:
    """Submit a new user message to an existing lead-agent thread."""
    response = await lead_agent_service.run_thread(
        thread_id=thread_id,
        user_id=current_user.id,
        content=request.content,
        organization_id=org_context.organization_id,
    )
    return LeadAgentThreadRunResponse(thread_id=thread_id, response=response)
