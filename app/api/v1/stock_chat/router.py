"""Stock-chat API router for phase-1 intake and clarification."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.repo import get_stock_chat_conversation_repo
from app.common.exceptions import (
    StockChatClarificationNotImplementedError,
    StockChatConversationNotFoundError,
)
from app.domain.models.user import User
from app.domain.schemas.stock_chat import (
    StockChatSendMessageRequest,
    StockChatSendMessageResponse,
)
from app.repo.stock_chat_conversation_repo import StockChatConversationRepository

router = APIRouter(prefix="/stock-chat", tags=["stock-chat"])


@router.post("/messages", response_model=StockChatSendMessageResponse)
async def send_stock_chat_message(
    request: StockChatSendMessageRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    conversation_repo: StockChatConversationRepository = Depends(
        get_stock_chat_conversation_repo
    ),
) -> StockChatSendMessageResponse:
    """Accept one stock-chat user turn for phase-1 clarification."""
    if request.conversation_id is not None:
        conversation = await conversation_repo.find_owned(
            conversation_id=request.conversation_id,
            user_id=current_user.id,
            organization_id=org_context.organization_id,
        )
        if conversation is None:
            raise StockChatConversationNotFoundError()

    raise StockChatClarificationNotImplementedError()
