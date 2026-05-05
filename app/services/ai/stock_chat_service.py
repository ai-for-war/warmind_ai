"""Service orchestration for stock-chat phase-1 intake and clarification."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.stock_chat_clarification_agent.agent import (
    create_stock_chat_clarification_agent,
)
from app.agents.implementations.stock_chat_clarification_agent.validation import (
    StockChatClarificationPayload,
    StockChatClarificationResult,
    parse_stock_chat_clarification_result,
)
from app.common.exceptions import (
    StockChatClarificationAgentError,
    StockChatConversationNotFoundError,
    StockChatDownstreamNotImplementedError,
)
from app.common.event_socket import StockChatEvents
from app.domain.models.stock_chat_conversation import StockChatConversation
from app.domain.models.stock_chat_message import (
    StockChatMessage,
    StockChatMessageRole,
)
from app.domain.schemas.stock_chat import (
    StockChatClarificationOptionResponse,
    StockChatClarificationRequiredResponse,
    StockChatClarificationResponse,
    StockChatSendMessageAcceptedResponse,
)
from app.repo.stock_chat_conversation_repo import StockChatConversationRepository
from app.repo.stock_chat_message_repo import StockChatMessageRepository
from app.socket_gateway import gateway

StockChatClarificationAgentFactory = Callable[[], CompiledStateGraph]
StockChatDownstreamHandler = Callable[
    [StockChatConversation, list[StockChatMessage]],
    Awaitable[None] | None,
]

logger = logging.getLogger(__name__)


class StockChatService:
    """Coordinate stock-chat persistence, clarification, and downstream handoff."""

    MAX_TITLE_LENGTH = 50

    def __init__(
        self,
        *,
        conversation_repo: StockChatConversationRepository,
        message_repo: StockChatMessageRepository,
        clarification_agent_factory: StockChatClarificationAgentFactory | None = None,
        downstream_handler: StockChatDownstreamHandler | None = None,
    ) -> None:
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self._clarification_agent_factory = (
            clarification_agent_factory or create_stock_chat_clarification_agent
        )
        self._downstream_handler = downstream_handler
        self._clarification_agent: CompiledStateGraph | None = None

    async def send_message(
        self,
        *,
        user_id: str,
        organization_id: str,
        content: str,
        conversation_id: str | None = None,
    ) -> StockChatSendMessageAcceptedResponse:
        """Persist one stock-chat turn and return an HTTP ACK immediately."""
        normalized_content = self._normalize_content(content)
        conversation = await self._get_or_create_conversation(
            user_id=user_id,
            organization_id=organization_id,
            content=normalized_content,
            conversation_id=conversation_id,
        )
        user_message = await self._append_message(
            conversation=conversation,
            role=StockChatMessageRole.USER,
            content=normalized_content,
        )
        return StockChatSendMessageAcceptedResponse(
            conversation_id=self._require_id(conversation.id),
            user_message_id=self._require_id(user_message.id),
        )

    async def process_clarification_response(
        self,
        *,
        user_id: str,
        organization_id: str,
        conversation_id: str,
        user_message_id: str,
    ) -> None:
        """Evaluate clarification in the background and emit socket updates."""
        try:
            conversation = await self.conversation_repo.find_owned(
                conversation_id=conversation_id,
                user_id=user_id,
                organization_id=organization_id,
            )
            if conversation is None:
                raise StockChatConversationNotFoundError()

            user_message = await self.message_repo.find_owned(
                message_id=user_message_id,
                user_id=user_id,
                organization_id=organization_id,
            )
            if user_message is None or user_message.conversation_id != conversation_id:
                raise StockChatClarificationAgentError(
                    "Stock-chat user message not found"
                )

            await self._process_clarification_result(
                user_id=user_id,
                organization_id=organization_id,
                conversation=conversation,
                user_message_id=user_message_id,
            )
        except StockChatDownstreamNotImplementedError as exc:
            logger.info(
                "Stock-chat downstream is not implemented for conversation %s",
                conversation_id,
            )
            await gateway.emit_to_user(
                user_id=user_id,
                event=StockChatEvents.FAILED,
                data={
                    "conversation_id": conversation_id,
                    "user_message_id": user_message_id,
                    "error": str(exc),
                },
                organization_id=organization_id,
            )
        except Exception as exc:
            logger.exception(
                "Error processing stock-chat clarification for conversation %s",
                conversation_id,
            )
            await gateway.emit_to_user(
                user_id=user_id,
                event=StockChatEvents.FAILED,
                data={
                    "conversation_id": conversation_id,
                    "user_message_id": user_message_id,
                    "error": str(exc),
                },
                organization_id=organization_id,
            )

    async def _process_clarification_result(
        self,
        *,
        user_id: str,
        organization_id: str,
        conversation: StockChatConversation,
        user_message_id: str,
    ) -> None:
        """Run clarification and emit the user-facing result when one exists."""
        history = await self._load_history(conversation)
        clarification_result = await self._invoke_clarification_agent(history)

        if clarification_result.status == "clarification_required":
            clarifications = clarification_result.clarification
            if not clarifications:
                raise StockChatClarificationAgentError()
            assistant_message = await self._persist_assistant_clarification(
                conversation=conversation,
                clarification=clarifications,
            )
            response = self._build_clarification_response(
                conversation_id=conversation.id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message.id,
                clarification=clarifications,
            )
            await gateway.emit_to_user(
                user_id=user_id,
                event=StockChatEvents.CLARIFICATION_REQUIRED,
                data=response.model_dump(mode="json"),
                organization_id=organization_id,
            )
            return

        await self._handoff_downstream(conversation=conversation, history=history)
        if self._downstream_handler is None:
            raise StockChatDownstreamNotImplementedError()

    async def _get_or_create_conversation(
        self,
        *,
        user_id: str,
        organization_id: str,
        content: str,
        conversation_id: str | None,
    ) -> StockChatConversation:
        """Create a new conversation or require an owned existing one."""
        if conversation_id is None:
            return await self.conversation_repo.create(
                user_id=user_id,
                organization_id=organization_id,
                title=self._generate_title_from_content(content),
            )

        conversation = await self.conversation_repo.find_owned(
            conversation_id=conversation_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        if conversation is None:
            raise StockChatConversationNotFoundError()
        return conversation

    async def _append_message(
        self,
        *,
        conversation: StockChatConversation,
        role: StockChatMessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> StockChatMessage:
        """Append one transcript message and update conversation activity."""
        message = await self.message_repo.create(
            conversation_id=self._require_id(conversation.id),
            user_id=conversation.user_id,
            organization_id=conversation.organization_id,
            role=role,
            content=content,
            metadata=metadata,
        )
        await self.conversation_repo.increment_message_count(
            conversation_id=self._require_id(conversation.id),
            user_id=conversation.user_id,
            organization_id=conversation.organization_id,
            last_message_at=message.created_at,
        )
        return message

    async def _load_history(
        self,
        conversation: StockChatConversation,
    ) -> list[StockChatMessage]:
        """Load full phase-1 transcript history in chronological order."""
        return await self.message_repo.get_by_conversation(
            conversation_id=self._require_id(conversation.id),
            user_id=conversation.user_id,
            organization_id=conversation.organization_id,
            limit=None,
        )

    async def _invoke_clarification_agent(
        self,
        history: list[StockChatMessage],
    ) -> StockChatClarificationResult:
        """Invoke the LangChain clarification agent and parse structured output."""
        try:
            result = await self._get_clarification_agent().ainvoke(
                {"messages": self._to_langchain_messages(history)}
            )
        except Exception as exc:
            raise StockChatClarificationAgentError(
                "Stock-chat clarification agent failed"
            ) from exc

        if not isinstance(result, Mapping) or "structured_response" not in result:
            raise StockChatClarificationAgentError(
                "Stock-chat clarification agent did not return structured_response"
            )

        try:
            return parse_stock_chat_clarification_result(result["structured_response"])
        except Exception as exc:
            raise StockChatClarificationAgentError(
                "Stock-chat clarification agent returned invalid structured output"
            ) from exc

    async def _persist_assistant_clarification(
        self,
        *,
        conversation: StockChatConversation,
        clarification: list[StockChatClarificationPayload],
    ) -> StockChatMessage:
        """Persist only user-facing clarification prompts as assistant messages."""
        metadata = {
            "kind": "stock_chat_clarification",
            "status": "clarification_required",
            "clarification": [
                clarification_item.model_dump(mode="json")
                for clarification_item in clarification
            ],
        }
        return await self._append_message(
            conversation=conversation,
            role=StockChatMessageRole.ASSISTANT,
            content=self._format_clarification_content(clarification),
            metadata=metadata,
        )

    async def _handoff_downstream(
        self,
        *,
        conversation: StockChatConversation,
        history: list[StockChatMessage],
    ) -> None:
        """Run the configured downstream handoff without invoking analyst agents."""
        if self._downstream_handler is None:
            return

        result = self._downstream_handler(conversation, history)
        if inspect.isawaitable(result):
            await result

    def _get_clarification_agent(self) -> CompiledStateGraph:
        """Return a lazily constructed clarification agent."""
        if self._clarification_agent is None:
            self._clarification_agent = self._clarification_agent_factory()
        return self._clarification_agent

    @classmethod
    def _to_langchain_messages(
        cls,
        messages: list[StockChatMessage],
    ) -> list[BaseMessage]:
        """Convert persisted stock-chat messages into LangChain message objects."""
        return [cls._to_langchain_message(message) for message in messages]

    @staticmethod
    def _to_langchain_message(message: StockChatMessage) -> BaseMessage:
        """Convert one stock-chat transcript message to a LangChain message."""
        if message.role == StockChatMessageRole.USER:
            return HumanMessage(content=message.content)
        if message.role == StockChatMessageRole.ASSISTANT:
            return AIMessage(content=message.content)
        if message.role == StockChatMessageRole.SYSTEM:
            return SystemMessage(content=message.content)
        return HumanMessage(content=message.content)

    @staticmethod
    def _build_clarification_response(
        *,
        conversation_id: str | None,
        user_message_id: str | None,
        assistant_message_id: str | None,
        clarification: list[StockChatClarificationPayload],
    ) -> StockChatClarificationRequiredResponse:
        """Build the user-facing clarification response payload."""
        return StockChatClarificationRequiredResponse(
            status="clarification_required",
            conversation_id=StockChatService._require_id(conversation_id),
            user_message_id=StockChatService._require_id(user_message_id),
            assistant_message_id=StockChatService._require_id(assistant_message_id),
            clarification=[
                StockChatClarificationResponse(
                    question=clarification_item.question,
                    options=[
                        StockChatClarificationOptionResponse(
                            id=option.id,
                            label=option.label,
                            description=option.description,
                        )
                        for option in clarification_item.options
                    ],
                )
                for clarification_item in clarification
            ],
        )

    @staticmethod
    def _format_clarification_content(
        clarification: list[StockChatClarificationPayload],
    ) -> str:
        """Render clarification text so short follow-up answers keep context."""
        sections: list[str] = []
        multiple_items = len(clarification) > 1
        for index, clarification_item in enumerate(clarification, start=1):
            question = clarification_item.question
            if multiple_items:
                question = f"{index}. {question}"
            option_lines = [
                f"- {option.label}: {option.description}"
                for option in clarification_item.options
            ]
            sections.append(
                "\n\n".join(
                    (
                        question,
                        "Options:\n" + "\n".join(option_lines),
                    )
                )
            )
        return "\n\n".join(sections)

    @classmethod
    def _generate_title_from_content(cls, content: str) -> str:
        """Create a deterministic title from the initial user message."""
        title = " ".join(content.strip().split())
        if len(title) > cls.MAX_TITLE_LENGTH:
            title = title[: cls.MAX_TITLE_LENGTH].rsplit(" ", 1)[0]
            if not title:
                title = content[: cls.MAX_TITLE_LENGTH].strip()
        return title or StockChatConversationRepository.DEFAULT_TITLE

    @staticmethod
    def _normalize_content(content: str) -> str:
        """Normalize user message content before persistence."""
        normalized = content.strip()
        if not normalized:
            raise ValueError("stock-chat message content must not be blank")
        return normalized

    @staticmethod
    def _require_id(value: str | None) -> str:
        """Require repository-created models to have an identifier."""
        if not value:
            raise StockChatClarificationAgentError("Stock-chat record id is missing")
        return value
