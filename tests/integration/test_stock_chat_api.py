from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.api.v1.stock_chat.router import router as stock_chat_router
from app.common.exceptions import AppException, StockChatConversationNotFoundError
from app.common.service import get_stock_chat_service
from app.domain.models.user import User, UserRole
from app.domain.schemas.stock_chat import StockChatSendMessageAcceptedResponse


def _user() -> User:
    return User(
        _id="user-1",
        email="user-1@example.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        created_at="2026-05-05T08:00:00Z",
        updated_at="2026-05-05T08:00:00Z",
    )


class _FakeStockChatService:
    def __init__(self) -> None:
        self.send_calls: list[dict[str, Any]] = []
        self.process_calls: list[dict[str, Any]] = []
        self.raise_on_send: Exception | None = None

    async def send_message(self, **kwargs: Any) -> StockChatSendMessageAcceptedResponse:
        self.send_calls.append(kwargs)
        if self.raise_on_send is not None:
            raise self.raise_on_send
        return StockChatSendMessageAcceptedResponse(
            conversation_id="stock-chat-conv-1",
            user_message_id="stock-chat-msg-1",
        )

    async def process_clarification_response(self, **kwargs: Any) -> None:
        self.process_calls.append(kwargs)


def _build_test_app(service: _FakeStockChatService) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exception_handler(_request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.include_router(stock_chat_router)
    app.dependency_overrides[get_current_active_user] = _user
    app.dependency_overrides[get_current_organization_context] = (
        lambda: OrganizationContext(organization_id="org-1")
    )
    app.dependency_overrides[get_stock_chat_service] = lambda: service
    return app


@pytest.mark.asyncio
async def test_stock_chat_message_endpoint_returns_ids_and_schedules_socket_processing() -> None:
    service = _FakeStockChatService()
    app = _build_test_app(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/stock-chat/messages",
            json={"content": "Should I buy VCB?"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "stock-chat-conv-1",
        "user_message_id": "stock-chat-msg-1",
    }
    assert service.send_calls == [
        {
            "user_id": "user-1",
            "organization_id": "org-1",
            "conversation_id": None,
            "content": "Should I buy VCB?",
        }
    ]
    assert service.process_calls == [
        {
            "user_id": "user-1",
            "organization_id": "org-1",
            "conversation_id": "stock-chat-conv-1",
            "user_message_id": "stock-chat-msg-1",
        }
    ]


@pytest.mark.asyncio
async def test_stock_chat_message_endpoint_rejects_inaccessible_conversation() -> None:
    service = _FakeStockChatService()
    service.raise_on_send = StockChatConversationNotFoundError()
    app = _build_test_app(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/stock-chat/messages",
            json={
                "conversation_id": "other-conversation",
                "content": "Follow up",
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Stock-chat conversation not found"}
    assert service.send_calls == [
        {
            "user_id": "user-1",
            "organization_id": "org-1",
            "conversation_id": "other-conversation",
            "content": "Follow up",
        }
    ]
    assert service.process_calls == []
