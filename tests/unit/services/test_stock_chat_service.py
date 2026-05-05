from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.common.event_socket import StockChatEvents
from app.common.exceptions import StockChatConversationNotFoundError
from app.domain.models.stock_chat_conversation import (
    StockChatConversation,
    StockChatConversationStatus,
)
from app.domain.models.stock_chat_message import (
    StockChatMessage,
    StockChatMessageRole,
)
from app.services.ai.stock_chat_service import StockChatService


def _utc_minute(minute: int) -> datetime:
    return datetime(2026, 5, 5, 8, minute, tzinfo=timezone.utc)


def _clarification_item(
    *,
    question: str,
    option_id: str,
    option_label: str,
    option_description: str,
) -> dict[str, Any]:
    return {
        "question": question,
        "options": [
            {
                "id": option_id,
                "label": option_label,
                "description": option_description,
            },
            {
                "id": f"{option_id}_other",
                "label": "Other",
                "description": "I want to answer in my own words.",
            },
        ],
    }


def _clarification_result(*items: dict[str, Any]) -> dict[str, Any]:
    return {
        "structured_response": {
            "status": "clarification_required",
            "clarification": list(items),
        }
    }


def _continue_result() -> dict[str, Any]:
    return {"structured_response": {"status": "continue"}}


class _InMemoryStockChatConversationRepo:
    def __init__(self) -> None:
        self.conversations: list[StockChatConversation] = []
        self.create_calls: list[dict[str, str]] = []

    async def create(
        self,
        *,
        user_id: str,
        organization_id: str,
        title: str | None = None,
    ) -> StockChatConversation:
        self.create_calls.append(
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "title": title or "Stock Chat",
            }
        )
        now = _utc_minute(len(self.conversations))
        conversation = StockChatConversation(
            _id=f"stock-chat-conv-{len(self.conversations) + 1}",
            user_id=user_id,
            organization_id=organization_id,
            title=title or "Stock Chat",
            status=StockChatConversationStatus.ACTIVE,
            message_count=0,
            last_message_at=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.conversations.append(conversation)
        return conversation

    async def find_owned(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
    ) -> StockChatConversation | None:
        for conversation in self.conversations:
            if (
                conversation.id == conversation_id
                and conversation.user_id == user_id
                and conversation.organization_id == organization_id
                and conversation.deleted_at is None
            ):
                return conversation
        return None

    async def increment_message_count(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
        last_message_at: datetime | None = None,
    ) -> StockChatConversation | None:
        conversation = await self.find_owned(
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        if conversation is None:
            return None
        conversation.message_count += 1
        conversation.last_message_at = last_message_at
        conversation.updated_at = last_message_at or conversation.updated_at
        return conversation


class _InMemoryStockChatMessageRepo:
    def __init__(self) -> None:
        self.messages: list[StockChatMessage] = []
        self.create_calls: list[dict[str, Any]] = []
        self.history_limits: list[int | None] = []

    async def create(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
        role: StockChatMessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> StockChatMessage:
        self.create_calls.append(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "role": role,
                "content": content,
                "metadata": metadata,
            }
        )
        message = StockChatMessage(
            _id=f"stock-chat-msg-{len(self.messages) + 1}",
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
            role=role,
            content=content,
            metadata=metadata,
            created_at=_utc_minute(len(self.messages)),
            deleted_at=None,
        )
        self.messages.append(message)
        return message

    async def get_by_conversation(
        self,
        *,
        conversation_id: str,
        user_id: str,
        organization_id: str,
        skip: int = 0,
        limit: int | None = 100,
    ) -> list[StockChatMessage]:
        self.history_limits.append(limit)
        messages = [
            message
            for message in self.messages
            if message.conversation_id == conversation_id
            and message.user_id == user_id
            and message.organization_id == organization_id
            and message.deleted_at is None
        ]
        messages.sort(key=lambda message: (message.created_at, message.id or ""))
        if skip:
            messages = messages[skip:]
        if limit is not None:
            messages = messages[:limit]
        return list(messages)

    async def find_owned(
        self,
        *,
        message_id: str,
        user_id: str,
        organization_id: str,
    ) -> StockChatMessage | None:
        for message in self.messages:
            if (
                message.id == message_id
                and message.user_id == user_id
                and message.organization_id == organization_id
                and message.deleted_at is None
            ):
                return message
        return None


class _FakeClarificationAgent:
    def __init__(self, *results: dict[str, Any]) -> None:
        self._results = list(results)
        self.invocations: list[dict[str, Any]] = []

    async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.invocations.append(payload)
        if not self._results:
            raise AssertionError("Unexpected clarification agent invocation")
        return self._results.pop(0)


class _FakeGateway:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit_to_user(
        self,
        *,
        user_id: str,
        event: str,
        data: dict[str, Any],
        organization_id: str | None = None,
    ) -> None:
        self.events.append(
            {
                "user_id": user_id,
                "event": event,
                "data": data,
                "organization_id": organization_id,
            }
        )


def _build_service(
    *,
    agent: _FakeClarificationAgent,
    conversation_repo: _InMemoryStockChatConversationRepo | None = None,
    message_repo: _InMemoryStockChatMessageRepo | None = None,
    downstream_calls: list[tuple[StockChatConversation, list[StockChatMessage]]]
    | None = None,
) -> tuple[
    StockChatService,
    _InMemoryStockChatConversationRepo,
    _InMemoryStockChatMessageRepo,
]:
    conversation_repo = conversation_repo or _InMemoryStockChatConversationRepo()
    message_repo = message_repo or _InMemoryStockChatMessageRepo()

    async def _downstream_handler(
        conversation: StockChatConversation,
        history: list[StockChatMessage],
    ) -> None:
        if downstream_calls is not None:
            downstream_calls.append((conversation, history))

    return (
        StockChatService(
            conversation_repo=conversation_repo,
            message_repo=message_repo,
            clarification_agent_factory=lambda: agent,
            downstream_handler=_downstream_handler
            if downstream_calls is not None
            else None,
        ),
        conversation_repo,
        message_repo,
    )


@pytest.mark.asyncio
async def test_first_message_persists_stock_chat_records_and_emits_missing_symbol(
    monkeypatch,
) -> None:
    import app.services.ai.stock_chat_service as stock_chat_service_module

    gateway = _FakeGateway()
    monkeypatch.setattr(stock_chat_service_module, "gateway", gateway)
    agent = _FakeClarificationAgent(
        _clarification_result(
            _clarification_item(
                question="Which stock or company do you want to discuss?",
                option_id="stock_vcb",
                option_label="VCB",
                option_description="I want to discuss VCB.",
            )
        )
    )
    service, conversation_repo, message_repo = _build_service(agent=agent)

    response = await service.send_message(
        user_id="user-1",
        organization_id="org-1",
        content="Should I buy?",
    )
    await service.process_clarification_response(
        user_id="user-1",
        organization_id="org-1",
        conversation_id=response.conversation_id,
        user_message_id=response.user_message_id,
    )

    assert response.model_dump() == {
        "conversation_id": "stock-chat-conv-1",
        "user_message_id": "stock-chat-msg-1",
    }
    assert conversation_repo.create_calls == [
        {
            "user_id": "user-1",
            "organization_id": "org-1",
            "title": "Should I buy?",
        }
    ]
    assert [message.role for message in message_repo.messages] == [
        StockChatMessageRole.USER,
        StockChatMessageRole.ASSISTANT,
    ]
    assert message_repo.messages[0].content == "Should I buy?"
    assert message_repo.messages[1].metadata is not None
    assert isinstance(message_repo.messages[1].metadata["clarification"], list)
    assert message_repo.history_limits == [None]
    assert len(agent.invocations[0]["messages"]) == 1
    assert gateway.events[0]["event"] == StockChatEvents.CLARIFICATION_REQUIRED
    assert gateway.events[0]["data"]["clarification"][0]["question"].startswith(
        "Which stock"
    )


@pytest.mark.asyncio
async def test_investment_decision_missing_time_horizon_emits_options(
    monkeypatch,
) -> None:
    import app.services.ai.stock_chat_service as stock_chat_service_module

    gateway = _FakeGateway()
    monkeypatch.setattr(stock_chat_service_module, "gateway", gateway)
    agent = _FakeClarificationAgent(
        _clarification_result(
            {
                "question": "What investment time horizon should I use?",
                "options": [
                    {
                        "id": "short_term",
                        "label": "Short term",
                        "description": "A few days to a few weeks.",
                    },
                    {
                        "id": "medium_term",
                        "label": "Medium term",
                        "description": "A few weeks to a few months.",
                    },
                    {
                        "id": "long_term",
                        "label": "Long term",
                        "description": "Six months or longer.",
                    },
                ],
            }
        )
    )
    service, _, _ = _build_service(agent=agent)

    response = await service.send_message(
        user_id="user-1",
        organization_id="org-1",
        content="Should I buy VCB?",
    )
    await service.process_clarification_response(
        user_id="user-1",
        organization_id="org-1",
        conversation_id=response.conversation_id,
        user_message_id=response.user_message_id,
    )

    clarification = gateway.events[0]["data"]["clarification"]
    assert clarification[0]["question"] == "What investment time horizon should I use?"
    assert [option["id"] for option in clarification[0]["options"]] == [
        "short_term",
        "medium_term",
        "long_term",
    ]
    assert "value" not in clarification[0]["options"][0]


@pytest.mark.asyncio
async def test_short_follow_up_is_evaluated_with_persisted_assistant_history(
    monkeypatch,
) -> None:
    import app.services.ai.stock_chat_service as stock_chat_service_module

    monkeypatch.setattr(stock_chat_service_module, "gateway", _FakeGateway())
    downstream_calls: list[tuple[StockChatConversation, list[StockChatMessage]]] = []
    agent = _FakeClarificationAgent(
        _clarification_result(
            _clarification_item(
                question="What investment time horizon should I use?",
                option_id="medium_term",
                option_label="Medium term",
                option_description="A few weeks to a few months.",
            )
        ),
        _continue_result(),
    )
    service, _, message_repo = _build_service(
        agent=agent,
        downstream_calls=downstream_calls,
    )

    first_response = await service.send_message(
        user_id="user-1",
        organization_id="org-1",
        content="Should I buy VCB?",
    )
    await service.process_clarification_response(
        user_id="user-1",
        organization_id="org-1",
        conversation_id=first_response.conversation_id,
        user_message_id=first_response.user_message_id,
    )
    follow_up_response = await service.send_message(
        user_id="user-1",
        organization_id="org-1",
        conversation_id=first_response.conversation_id,
        content="Medium term",
    )
    await service.process_clarification_response(
        user_id="user-1",
        organization_id="org-1",
        conversation_id=follow_up_response.conversation_id,
        user_message_id=follow_up_response.user_message_id,
    )

    second_invocation_messages = agent.invocations[1]["messages"]
    assert [message.type for message in second_invocation_messages] == [
        "human",
        "ai",
        "human",
    ]
    assert "What investment time horizon" in second_invocation_messages[1].content
    assert second_invocation_messages[2].content == "Medium term"
    assert [message.role for message in message_repo.messages] == [
        StockChatMessageRole.USER,
        StockChatMessageRole.ASSISTANT,
        StockChatMessageRole.USER,
    ]
    assert len(downstream_calls) == 1
    assert [message.content for message in downstream_calls[0][1]] == [
        "Should I buy VCB?",
        message_repo.messages[1].content,
        "Medium term",
    ]


@pytest.mark.asyncio
async def test_sufficient_context_hands_off_without_readiness_or_assistant_message(
    monkeypatch,
) -> None:
    import app.services.ai.stock_chat_service as stock_chat_service_module

    gateway = _FakeGateway()
    monkeypatch.setattr(stock_chat_service_module, "gateway", gateway)
    downstream_calls: list[tuple[StockChatConversation, list[StockChatMessage]]] = []
    agent = _FakeClarificationAgent(_continue_result())
    service, _, message_repo = _build_service(
        agent=agent,
        downstream_calls=downstream_calls,
    )

    response = await service.send_message(
        user_id="user-1",
        organization_id="org-1",
        content="Analyze VCB for a three month buy decision.",
    )
    await service.process_clarification_response(
        user_id="user-1",
        organization_id="org-1",
        conversation_id=response.conversation_id,
        user_message_id=response.user_message_id,
    )

    assert response.model_dump() == {
        "conversation_id": "stock-chat-conv-1",
        "user_message_id": "stock-chat-msg-1",
    }
    assert [message.role for message in message_repo.messages] == [
        StockChatMessageRole.USER
    ]
    assert gateway.events == []
    assert len(downstream_calls) == 1
    assert downstream_calls[0][1][0].content == (
        "Analyze VCB for a three month buy decision."
    )


@pytest.mark.asyncio
async def test_cross_scope_conversation_is_rejected_before_appending_message() -> None:
    agent = _FakeClarificationAgent(_continue_result())
    conversation_repo = _InMemoryStockChatConversationRepo()
    message_repo = _InMemoryStockChatMessageRepo()
    other_conversation = await conversation_repo.create(
        user_id="user-2",
        organization_id="org-1",
        title="Other user",
    )
    service, _, _ = _build_service(
        agent=agent,
        conversation_repo=conversation_repo,
        message_repo=message_repo,
    )

    with pytest.raises(StockChatConversationNotFoundError):
        await service.send_message(
            user_id="user-1",
            organization_id="org-1",
            conversation_id=other_conversation.id,
            content="Follow up",
        )

    assert message_repo.messages == []
    assert agent.invocations == []


@pytest.mark.asyncio
async def test_cross_organization_conversation_is_rejected_before_appending_message() -> None:
    agent = _FakeClarificationAgent(_continue_result())
    conversation_repo = _InMemoryStockChatConversationRepo()
    message_repo = _InMemoryStockChatMessageRepo()
    other_conversation = await conversation_repo.create(
        user_id="user-1",
        organization_id="org-2",
        title="Other org",
    )
    service, _, _ = _build_service(
        agent=agent,
        conversation_repo=conversation_repo,
        message_repo=message_repo,
    )

    with pytest.raises(StockChatConversationNotFoundError):
        await service.send_message(
            user_id="user-1",
            organization_id="org-1",
            conversation_id=other_conversation.id,
            content="Follow up",
        )

    assert message_repo.messages == []
    assert agent.invocations == []
