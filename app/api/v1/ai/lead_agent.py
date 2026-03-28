"""Lead-agent API endpoints for conversation-centric execution."""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.service import get_lead_agent_service
from app.domain.models.conversation import ConversationStatus
from app.domain.models.user import User
from app.domain.schemas.lead_agent import (
    LeadAgentConversationListResponse,
    LeadAgentConversationResponse,
    LeadAgentMessageListResponse,
    LeadAgentMessageResponse,
    LeadAgentSendMessageRequest,
    LeadAgentSendMessageResponse,
)
from app.services.ai.lead_agent_service import LeadAgentService

router = APIRouter(prefix="/lead-agent", tags=["lead-agent"])


@router.post("/messages", response_model=LeadAgentSendMessageResponse)
async def send_message(
    request: LeadAgentSendMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    lead_agent_service: LeadAgentService = Depends(get_lead_agent_service),
) -> LeadAgentSendMessageResponse:
    """Accept a lead-agent turn and process the response asynchronously."""
    user_message_id, conversation_id = await lead_agent_service.send_message(
        user_id=current_user.id,
        content=request.content,
        conversation_id=request.conversation_id,
        organization_id=org_context.organization_id,
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
