"""Chat API endpoints for sending messages and receiving AI responses.

Provides REST endpoints for:
- Sending messages to AI agent
- Triggering background processing for agent responses
- Listing user conversations with pagination and filtering
"""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.service import get_chat_service
from app.domain.models.conversation import ConversationStatus
from app.domain.models.user import User
from app.domain.schemas.chat import (
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    MessageResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services.ai.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/messages", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    chat_service: ChatService = Depends(get_chat_service),
) -> SendMessageResponse:
    """Send a message and trigger async agent processing.

    If conversation_id is not provided, creates a new conversation.
    The user message is saved immediately, and agent processing
    runs in the background with responses streamed via Socket.IO.

    Args:
        request: SendMessageRequest with content and optional conversation_id
        background_tasks: FastAPI BackgroundTasks for async processing
        current_user: Authenticated user from JWT token
        chat_service: ChatService dependency

    Returns:
        SendMessageResponse with user_message_id and conversation_id

    Raises:
        HTTPException: 404 if conversation_id is invalid or not found

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
    """
    user_id = current_user.id

    # Validate conversation exists if conversation_id is provided
    if request.conversation_id is not None:
        conversation = await chat_service.conversation_service.get_conversation(
            request.conversation_id,
            organization_id=org_context.organization_id,
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        # Verify user owns the conversation
        if conversation.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

    # Save user message and get/create conversation
    user_message_id, conversation_id = await chat_service.send_message(
        user_id=user_id,
        content=request.content,
        conversation_id=request.conversation_id,
        organization_id=org_context.organization_id,
    )

    # Add background task to process agent response
    background_tasks.add_task(
        chat_service.process_agent_response,
        user_id=user_id,
        conversation_id=conversation_id,
        organization_id=org_context.organization_id,
    )

    return SendMessageResponse(
        user_message_id=user_message_id,
        conversation_id=conversation_id,
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[ConversationStatus] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    chat_service: ChatService = Depends(get_chat_service),
) -> ConversationListResponse:
    """List conversations for the authenticated user.

    Supports pagination, status filtering, and title search.
    Results are sorted by updated_at descending (most recent first).

    Args:
        skip: Number of records to skip (default 0)
        limit: Maximum number of records to return (default 20, max 100)
        status: Optional status filter (active/archived)
        search: Optional title search query (max 100 chars)
        current_user: Authenticated user from JWT token
        chat_service: ChatService dependency

    Returns:
        ConversationListResponse with items, total, skip, and limit

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
    """
    result = await chat_service.search_conversations(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        status=status,
        search=search,
        skip=skip,
        limit=limit,
    )

    return ConversationListResponse(
        items=[
            ConversationResponse(
                id=conv.id,
                title=conv.title,
                status=conv.status,
                message_count=conv.message_count,
                last_message_at=conv.last_message_at,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
            for conv in result.items
        ],
        total=result.total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/conversations/{conversation_id}/messages", response_model=MessageListResponse
)
async def get_conversation_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    chat_service: ChatService = Depends(get_chat_service),
) -> MessageListResponse:
    """Get all messages for a conversation.

    Returns messages sorted by created_at ascending (oldest first).
    Includes full metadata and attachments.

    Args:
        conversation_id: ID of the conversation
        current_user: Authenticated user from JWT token
        chat_service: ChatService dependency

    Returns:
        MessageListResponse with conversation_id and messages

    Raises:
        HTTPException: 404 if conversation not found or not owned by user

    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
    """
    # Verify conversation exists and user owns it
    conversation = await chat_service.conversation_service.get_conversation(
        conversation_id,
        organization_id=org_context.organization_id,
    )
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Get all messages (no pagination needed per requirements)
    messages = await chat_service.conversation_service.get_messages(
        conversation_id=conversation_id
    )

    return MessageListResponse(
        conversation_id=conversation_id,
        messages=[
            MessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                attachments=msg.attachments,
                metadata=msg.metadata,
                is_complete=msg.is_complete,
                created_at=msg.created_at,
            )
            for msg in messages
        ],
    )
