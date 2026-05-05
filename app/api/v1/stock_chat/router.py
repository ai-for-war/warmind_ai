"""Stock-chat API router for phase-1 intake and clarification."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.service import get_stock_chat_service
from app.domain.models.user import User
from app.domain.schemas.stock_chat import (
    StockChatSendMessageRequest,
    StockChatSendMessageResponse,
)
from app.services.ai.stock_chat_service import StockChatService

router = APIRouter(prefix="/stock-chat", tags=["stock-chat"])


@router.post("/messages", response_model=StockChatSendMessageResponse)
async def send_stock_chat_message(
    request: StockChatSendMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    stock_chat_service: StockChatService = Depends(get_stock_chat_service),
) -> StockChatSendMessageResponse:
    """Accept one stock-chat user turn for phase-1 clarification."""
    response = await stock_chat_service.send_message(
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        conversation_id=request.conversation_id,
        content=request.content,
    )
    background_tasks.add_task(
        stock_chat_service.process_clarification_response,
        user_id=current_user.id,
        organization_id=org_context.organization_id,
        conversation_id=response.conversation_id,
        user_message_id=response.user_message_id,
    )
    return response
