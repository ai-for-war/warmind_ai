"""Schemas for stock-chat intake and clarification API payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.domain.schemas.stock import StockSchemaBase


class StockChatSendMessageRequest(StockSchemaBase):
    """Request payload for submitting one stock-chat user turn."""

    conversation_id: str | None = Field(default=None, min_length=1)
    content: str = Field(..., min_length=1, max_length=10000)


class StockChatSendMessageAcceptedResponse(StockSchemaBase):
    """HTTP response returned after the user turn is accepted for processing."""

    conversation_id: str = Field(..., min_length=1)
    user_message_id: str = Field(..., min_length=1)


class StockChatClarificationOptionResponse(StockSchemaBase):
    """One user-facing suggested answer for a clarification prompt."""

    id: str = Field(..., min_length=1, max_length=100)
    label: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=1000)


class StockChatClarificationResponse(StockSchemaBase):
    """One user-facing clarification payload emitted when context is missing."""

    question: str = Field(..., min_length=1, max_length=1000)
    options: list[StockChatClarificationOptionResponse] = Field(
        ...,
        min_length=2,
        max_length=4,
    )


class StockChatClarificationRequiredResponse(StockSchemaBase):
    """Socket payload emitted when the user must provide more context."""

    status: Literal["clarification_required"]
    conversation_id: str = Field(..., min_length=1)
    user_message_id: str = Field(..., min_length=1)
    assistant_message_id: str = Field(..., min_length=1)
    clarification: list[StockChatClarificationResponse] = Field(
        ...,
        min_length=1,
        max_length=3,
    )


StockChatSendMessageResponse = StockChatSendMessageAcceptedResponse
