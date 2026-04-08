"""Lead-agent API endpoints for conversation-centric execution."""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.agents.implementations.lead_agent.runtime import (
    get_default_lead_agent_runtime_config,
    get_lead_agent_runtime_catalog,
)
from app.common.service import get_lead_agent_service, get_lead_agent_skill_service
from app.domain.models.conversation import ConversationStatus
from app.domain.models.user import User
from app.domain.schemas.lead_agent import (
    LeadAgentCatalogModelResponse,
    LeadAgentCatalogProviderResponse,
    LeadAgentCatalogResponse,
    LeadAgentCreateSkillRequest,
    LeadAgentConversationListResponse,
    LeadAgentPlanResponse,
    LeadAgentConversationResponse,
    LeadAgentMessageListResponse,
    LeadAgentMessageResponse,
    LeadAgentSendMessageRequest,
    LeadAgentSendMessageResponse,
    LeadAgentSkillEnablementResponse,
    LeadAgentSkillFilterStatus,
    LeadAgentSkillListResponse,
    LeadAgentSkillResponse,
    LeadAgentToolListResponse,
    LeadAgentUpdateSkillRequest,
)
from app.services.ai.lead_agent_service import LeadAgentService
from app.services.ai.lead_agent_skill_service import LeadAgentSkillService

router = APIRouter(prefix="/lead-agent", tags=["lead-agent"])


@router.get("/catalog", response_model=LeadAgentCatalogResponse)
async def get_catalog(
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
) -> LeadAgentCatalogResponse:
    """Return the supported provider/model/reasoning catalog for lead-agent."""
    default_runtime = get_default_lead_agent_runtime_config()
    catalog = get_lead_agent_runtime_catalog()

    return LeadAgentCatalogResponse(
        default_provider=default_runtime.provider,
        default_model=default_runtime.model,
        default_reasoning=default_runtime.reasoning,
        providers=[
            LeadAgentCatalogProviderResponse(
                provider=provider.provider,
                display_name=provider.display_name,
                is_default=provider.is_default,
                models=[
                    LeadAgentCatalogModelResponse(
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


@router.get("/tools", response_model=LeadAgentToolListResponse)
async def list_tools(
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_skill_service: LeadAgentSkillService = Depends(
        get_lead_agent_skill_service
    ),
) -> LeadAgentToolListResponse:
    """List the currently available user-selectable lead-agent tools."""
    return await lead_agent_skill_service.list_tools()


@router.get("/skills", response_model=LeadAgentSkillListResponse)
async def list_skills(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=100),
    skill_filter: LeadAgentSkillFilterStatus = Query(
        default=LeadAgentSkillFilterStatus.ALL,
        alias="filter",
    ),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_skill_service: LeadAgentSkillService = Depends(
        get_lead_agent_skill_service
    ),
) -> LeadAgentSkillListResponse:
    """List the caller's lead-agent skills in the current organization."""
    return await lead_agent_skill_service.list_skills(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        search=search,
        skill_filter=skill_filter,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/skills",
    response_model=LeadAgentSkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_skill(
    request: LeadAgentCreateSkillRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_skill_service: LeadAgentSkillService = Depends(
        get_lead_agent_skill_service
    ),
) -> LeadAgentSkillResponse:
    """Create one caller-owned lead-agent skill."""
    return await lead_agent_skill_service.create_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        request=request,
    )


@router.get("/skills/{skill_id}", response_model=LeadAgentSkillResponse)
async def get_skill(
    skill_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_skill_service: LeadAgentSkillService = Depends(
        get_lead_agent_skill_service
    ),
) -> LeadAgentSkillResponse:
    """Get one caller-owned lead-agent skill."""
    return await lead_agent_skill_service.get_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        skill_id=skill_id,
    )


@router.patch("/skills/{skill_id}", response_model=LeadAgentSkillResponse)
async def update_skill(
    skill_id: str,
    request: LeadAgentUpdateSkillRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_skill_service: LeadAgentSkillService = Depends(
        get_lead_agent_skill_service
    ),
) -> LeadAgentSkillResponse:
    """Update one caller-owned lead-agent skill."""
    return await lead_agent_skill_service.update_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        skill_id=skill_id,
        request=request,
    )


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_skill_service: LeadAgentSkillService = Depends(
        get_lead_agent_skill_service
    ),
) -> None:
    """Delete one caller-owned lead-agent skill."""
    await lead_agent_skill_service.delete_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        skill_id=skill_id,
    )


@router.put(
    "/skills/{skill_id}/enabled",
    response_model=LeadAgentSkillEnablementResponse,
)
async def enable_skill(
    skill_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_skill_service: LeadAgentSkillService = Depends(
        get_lead_agent_skill_service
    ),
) -> LeadAgentSkillEnablementResponse:
    """Enable one caller-owned lead-agent skill for the current organization."""
    return await lead_agent_skill_service.enable_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        skill_id=skill_id,
    )


@router.delete(
    "/skills/{skill_id}/enabled",
    response_model=LeadAgentSkillEnablementResponse,
)
async def disable_skill(
    skill_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_skill_service: LeadAgentSkillService = Depends(
        get_lead_agent_skill_service
    ),
) -> LeadAgentSkillEnablementResponse:
    """Disable one caller-owned lead-agent skill for the current organization."""
    return await lead_agent_skill_service.disable_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        skill_id=skill_id,
    )


@router.post("/messages", response_model=LeadAgentSendMessageResponse)
async def send_message(
    request: LeadAgentSendMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_service: LeadAgentService = Depends(get_lead_agent_service),
) -> LeadAgentSendMessageResponse:
    """Accept a lead-agent turn and process the response asynchronously."""
    lead_agent_service.configure_runtime(
        provider=request.provider,
        model=request.model,
        reasoning=request.reasoning,
    )
    user_message_id, conversation_id = await lead_agent_service.send_message(
        user_id=current_user.id,
        content=request.content,
        conversation_id=request.conversation_id,
        organization_id=org_context.organization_id,
        subagent_enabled=request.subagent_enabled,
    )
    background_tasks.add_task(
        lead_agent_service.process_agent_response,
        user_id=current_user.id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        organization_id=org_context.organization_id,
    )
    return LeadAgentSendMessageResponse(
        user_message_id=user_message_id,
        conversation_id=conversation_id,
    )


@router.get("/conversations", response_model=LeadAgentConversationListResponse)
async def list_conversations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[ConversationStatus] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_service: LeadAgentService = Depends(get_lead_agent_service),
) -> LeadAgentConversationListResponse:
    """List lead-agent conversations for the authenticated caller."""
    result = await lead_agent_service.search_conversations(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        status=status,
        search=search,
        skip=skip,
        limit=limit,
    )
    return LeadAgentConversationListResponse(
        items=[
            LeadAgentConversationResponse(
                id=conversation.id,
                title=conversation.title,
                status=conversation.status,
                message_count=conversation.message_count,
                last_message_at=conversation.last_message_at,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                thread_id=conversation.thread_id,
            )
            for conversation in result.items
        ],
        total=result.total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=LeadAgentMessageListResponse,
)
async def get_conversation_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_service: LeadAgentService = Depends(get_lead_agent_service),
) -> LeadAgentMessageListResponse:
    """Return persisted message history for a lead-agent conversation."""
    messages = await lead_agent_service.get_conversation_messages(
        conversation_id=conversation_id,
        user_id=current_user.id,
        organization_id=org_context.organization_id,
    )
    return LeadAgentMessageListResponse(
        conversation_id=conversation_id,
        messages=[
            LeadAgentMessageResponse(
                id=message.id,
                role=message.role,
                content=message.content,
                attachments=message.attachments,
                metadata=message.metadata,
                is_complete=message.is_complete,
                created_at=message.created_at,
                thread_id=message.thread_id,
            )
            for message in messages
        ],
    )


@router.get(
    "/conversations/{conversation_id}/plan",
    response_model=LeadAgentPlanResponse,
)
async def get_conversation_plan(
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_service: LeadAgentService = Depends(get_lead_agent_service),
) -> LeadAgentPlanResponse:
    """Return the latest persisted plan snapshot for a lead-agent conversation."""
    plan = await lead_agent_service.get_conversation_plan(
        conversation_id=conversation_id,
        user_id=current_user.id,
        organization_id=org_context.organization_id,
    )
    return LeadAgentPlanResponse.model_validate(plan)
