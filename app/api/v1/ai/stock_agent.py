"""Stock-agent API endpoints for conversation-centric execution."""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.agents.implementations.stock_agent.runtime import (
    get_default_stock_agent_runtime_config,
    get_stock_agent_runtime_catalog,
)
from app.common.service import get_stock_agent_service, get_stock_agent_skill_service
from app.domain.models.conversation import ConversationStatus
from app.domain.models.user import User
from app.domain.schemas.stock_agent import (
    StockAgentCatalogModelResponse,
    StockAgentCatalogProviderResponse,
    StockAgentCatalogResponse,
    StockAgentCreateSkillRequest,
    StockAgentConversationListResponse,
    StockAgentPlanResponse,
    StockAgentConversationResponse,
    StockAgentMessageListResponse,
    StockAgentMessageResponse,
    StockAgentSendMessageRequest,
    StockAgentSendMessageResponse,
    StockAgentSkillEnablementResponse,
    StockAgentSkillFilterStatus,
    StockAgentSkillListResponse,
    StockAgentSkillResponse,
    StockAgentToolListResponse,
    StockAgentUpdateSkillRequest,
)
from app.services.ai.stock_agent_service import StockAgentService
from app.services.ai.stock_agent_skill_service import StockAgentSkillService

router = APIRouter(prefix="/stock-agent", tags=["stock-agent"])


@router.get("/catalog", response_model=StockAgentCatalogResponse)
async def get_catalog(
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
) -> StockAgentCatalogResponse:
    """Return the supported provider/model/reasoning catalog for stock-agent."""
    default_runtime = get_default_stock_agent_runtime_config()
    catalog = get_stock_agent_runtime_catalog()

    return StockAgentCatalogResponse(
        default_provider=default_runtime.provider,
        default_model=default_runtime.model,
        default_reasoning=default_runtime.reasoning,
        providers=[
            StockAgentCatalogProviderResponse(
                provider=provider.provider,
                display_name=provider.display_name,
                is_default=provider.is_default,
                models=[
                    StockAgentCatalogModelResponse(
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


@router.get("/tools", response_model=StockAgentToolListResponse)
async def list_tools(
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_skill_service: StockAgentSkillService = Depends(
        get_stock_agent_skill_service
    ),
) -> StockAgentToolListResponse:
    """List the currently available user-selectable stock-agent tools."""
    return await stock_agent_skill_service.list_tools()


@router.get("/skills", response_model=StockAgentSkillListResponse)
async def list_skills(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=100),
    skill_filter: StockAgentSkillFilterStatus = Query(
        default=StockAgentSkillFilterStatus.ALL,
        alias="filter",
    ),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_skill_service: StockAgentSkillService = Depends(
        get_stock_agent_skill_service
    ),
) -> StockAgentSkillListResponse:
    """List the caller's stock-agent skills in the current organization."""
    return await stock_agent_skill_service.list_skills(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        search=search,
        skill_filter=skill_filter,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/skills",
    response_model=StockAgentSkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_skill(
    request: StockAgentCreateSkillRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_skill_service: StockAgentSkillService = Depends(
        get_stock_agent_skill_service
    ),
) -> StockAgentSkillResponse:
    """Create one caller-owned stock-agent skill."""
    return await stock_agent_skill_service.create_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        request=request,
    )


@router.get("/skills/{skill_id}", response_model=StockAgentSkillResponse)
async def get_skill(
    skill_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_skill_service: StockAgentSkillService = Depends(
        get_stock_agent_skill_service
    ),
) -> StockAgentSkillResponse:
    """Get one caller-owned stock-agent skill."""
    return await stock_agent_skill_service.get_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        skill_id=skill_id,
    )


@router.patch("/skills/{skill_id}", response_model=StockAgentSkillResponse)
async def update_skill(
    skill_id: str,
    request: StockAgentUpdateSkillRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_skill_service: StockAgentSkillService = Depends(
        get_stock_agent_skill_service
    ),
) -> StockAgentSkillResponse:
    """Update one caller-owned stock-agent skill."""
    return await stock_agent_skill_service.update_skill(
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
    stock_agent_skill_service: StockAgentSkillService = Depends(
        get_stock_agent_skill_service
    ),
) -> None:
    """Delete one caller-owned stock-agent skill."""
    await stock_agent_skill_service.delete_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        skill_id=skill_id,
    )


@router.put(
    "/skills/{skill_id}/enabled",
    response_model=StockAgentSkillEnablementResponse,
)
async def enable_skill(
    skill_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_skill_service: StockAgentSkillService = Depends(
        get_stock_agent_skill_service
    ),
) -> StockAgentSkillEnablementResponse:
    """Enable one caller-owned stock-agent skill for the current organization."""
    return await stock_agent_skill_service.enable_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        skill_id=skill_id,
    )


@router.delete(
    "/skills/{skill_id}/enabled",
    response_model=StockAgentSkillEnablementResponse,
)
async def disable_skill(
    skill_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_skill_service: StockAgentSkillService = Depends(
        get_stock_agent_skill_service
    ),
) -> StockAgentSkillEnablementResponse:
    """Disable one caller-owned stock-agent skill for the current organization."""
    return await stock_agent_skill_service.disable_skill(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        skill_id=skill_id,
    )


@router.post("/messages", response_model=StockAgentSendMessageResponse)
async def send_message(
    request: StockAgentSendMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_service: StockAgentService = Depends(get_stock_agent_service),
) -> StockAgentSendMessageResponse:
    """Accept a stock-agent turn and process the response asynchronously."""
    stock_agent_service.configure_runtime(
        provider=request.provider,
        model=request.model,
        reasoning=request.reasoning,
    )
    user_message_id, conversation_id = await stock_agent_service.send_message(
        user_id=current_user.id,
        content=request.content,
        conversation_id=request.conversation_id,
        organization_id=org_context.organization_id,
        subagent_enabled=request.subagent_enabled,
    )
    background_tasks.add_task(
        stock_agent_service.process_agent_response,
        user_id=current_user.id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        organization_id=org_context.organization_id,
    )
    return StockAgentSendMessageResponse(
        user_message_id=user_message_id,
        conversation_id=conversation_id,
    )


@router.get("/conversations", response_model=StockAgentConversationListResponse)
async def list_conversations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[ConversationStatus] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_service: StockAgentService = Depends(get_stock_agent_service),
) -> StockAgentConversationListResponse:
    """List stock-agent conversations for the authenticated caller."""
    result = await stock_agent_service.search_conversations(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        status=status,
        search=search,
        skip=skip,
        limit=limit,
    )
    return StockAgentConversationListResponse(
        items=[
            StockAgentConversationResponse(
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
    response_model=StockAgentMessageListResponse,
)
async def get_conversation_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_service: StockAgentService = Depends(get_stock_agent_service),
) -> StockAgentMessageListResponse:
    """Return persisted message history for a stock-agent conversation."""
    messages = await stock_agent_service.get_conversation_messages(
        conversation_id=conversation_id,
        user_id=current_user.id,
        organization_id=org_context.organization_id,
    )
    return StockAgentMessageListResponse(
        conversation_id=conversation_id,
        messages=[
            StockAgentMessageResponse(
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
    response_model=StockAgentPlanResponse,
)
async def get_conversation_plan(
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_agent_service: StockAgentService = Depends(get_stock_agent_service),
) -> StockAgentPlanResponse:
    """Return the latest persisted plan snapshot for a stock-agent conversation."""
    plan = await stock_agent_service.get_conversation_plan(
        conversation_id=conversation_id,
        user_id=current_user.id,
        organization_id=org_context.organization_id,
    )
    return StockAgentPlanResponse.model_validate(plan)
