"""Conversation service for managing conversations and messages.

Provides business logic for conversation management including:
- Creating conversations with auto-generated titles
- Adding messages with conversation stats updates
- LangChain compatibility for AI integration
"""

import logging
from collections.abc import Callable
from typing import Any, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import BaseModel, Field

from app.domain.models.conversation import ConversationStatus
from app.domain.models.stock_agent_conversation import StockAgentConversation
from app.domain.models.message import (
    Attachment,
    Message,
    MessageMetadata,
    MessageRole,
)
from app.infrastructure.llm.factory import get_chat_azure_openai_legacy
from app.repo.stock_agent_conversation_repo import (
    StockAgentConversationRepository,
    StockAgentConversationSearchResult,
)
from app.repo.stock_agent_message_repo import StockAgentMessageRepository

logger = logging.getLogger(__name__)


class GeneratedConversationTitle(BaseModel):
    """Structured output schema for initial conversation titles."""

    title: str = Field(
        description=(
            "A concise conversation title in the same language as the user message"
        )
    )


class StockAgentConversationService:
    """Service for managing conversations and messages.

    Handles business logic including:
    - Auto title generation for new conversations
    - Updating conversation stats when messages are added
    - Converting messages to LangChain format
    """

    DEFAULT_TITLE = "New Conversation"
    MAX_TITLE_LENGTH = 50
    MAX_TITLE_SOURCE_LENGTH = 2000
    TITLE_GENERATION_PROMPT = (
        "You generate titles for brand new chat conversations.\n"
        "Return one concise, specific title that reflects the user's first message.\n"
        "Rules:\n"
        "- Use the same language as the user.\n"
        "- Prefer 3 to 8 words.\n"
        "- Do not use quotation marks.\n"
        "- Do not add emojis.\n"
        "- Do not end with punctuation.\n"
        "- Avoid generic titles like 'New chat' or 'Question'."
    )

    def __init__(
        self,
        conversation_repo: StockAgentConversationRepository,
        message_repo: StockAgentMessageRepository,
        llm_factory: Callable[[], Any] | None = None,
    ):
        """Initialize StockAgentConversationService with repositories.

        Args:
            conversation_repo: Repository for conversation operations
            message_repo: Repository for message operations
        """
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self._llm_factory = llm_factory or self._default_title_llm_factory
        self._structured_title_llm: Any | None = None

    async def create_conversation(
        self,
        user_id: str,
        title: Optional[str] = None,
        organization_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> StockAgentConversation:
        """Create a new conversation record.

        Args:
            user_id: ID of the user creating the conversation
            title: Optional title for the conversation
            thread_id: Optional runtime thread mapping for stock-agent projections

        Returns:
            Created StockAgentConversation instance

        Requirements: 4.1
        """
        return await self.conversation_repo.create(
            user_id=user_id,
            title=title,
            organization_id=organization_id,
            thread_id=thread_id,
        )

    async def create_conversation_from_initial_message(
        self,
        user_id: str,
        content: str,
        organization_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> StockAgentConversation:
        """Create a conversation and derive its initial title from first message."""
        title = await self.generate_initial_title(content)
        return await self.create_conversation(
            user_id=user_id,
            title=title,
            organization_id=organization_id,
            thread_id=thread_id,
        )

    async def generate_initial_title(self, content: str) -> str:
        """Generate a title for the very first message in a conversation."""
        normalized_content = content.strip()
        if not normalized_content:
            return self.DEFAULT_TITLE

        try:
            result = await self._get_structured_title_llm().ainvoke(
                [
                    SystemMessage(content=self.TITLE_GENERATION_PROMPT),
                    HumanMessage(
                        content=normalized_content[: self.MAX_TITLE_SOURCE_LENGTH]
                    ),
                ]
            )
            if isinstance(result, GeneratedConversationTitle):
                raw_title = result.title
            elif isinstance(result, dict):
                raw_title = str(result.get("title", ""))
            else:
                raw_title = str(getattr(result, "title", result))
            normalized_title = self._normalize_generated_title(raw_title)
            if normalized_title:
                return normalized_title
        except Exception:
            logger.exception("Failed to generate initial conversation title")

        return self._generate_title_from_content(normalized_content)

    async def add_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        organization_id: Optional[str] = None,
        attachments: Optional[list[Attachment]] = None,
        metadata: Optional[MessageMetadata] = None,
        thread_id: Optional[str] = None,
        is_complete: bool = True,
    ) -> Message:
        """Add a message to a conversation and update conversation stats.

        Args:
            conversation_id: ID of the conversation
            role: Role of the message sender
            content: Message content text
            attachments: Optional list of attachments
            metadata: Optional AI metadata
            thread_id: Optional runtime thread mapping for stock-agent projections
            is_complete: Whether the message is complete (False for streaming)

        Returns:
            Created Message instance

        Requirements: 2.6, 4.2
        """
        # Create the message
        message = await self.message_repo.create(
            conversation_id=conversation_id,
            role=role,
            content=content,
            attachments=attachments,
            metadata=metadata,
            thread_id=thread_id,
            is_complete=is_complete,
        )

        # Update conversation stats (message_count and last_message_at)
        await self.conversation_repo.increment_message_count(
            conversation_id=conversation_id,
            last_message_at=message.created_at,
            organization_id=organization_id,
        )

        return message

    def _generate_title_from_content(self, content: str) -> str:
        """Generate a title from message content.

        Truncates content to MAX_TITLE_LENGTH characters.

        Args:
            content: Message content to derive title from

        Returns:
            Generated title (truncated if necessary)

        Requirements: 4.2
        """
        # Strip whitespace and truncate
        title = content.strip()
        if len(title) > self.MAX_TITLE_LENGTH:
            # Truncate at word boundary
            title = title[: self.MAX_TITLE_LENGTH].rsplit(" ", 1)[0]
            if not title:  # If no space found, just truncate
                title = content[: self.MAX_TITLE_LENGTH]
        return title if title else self.DEFAULT_TITLE

    def _normalize_generated_title(self, title: str) -> str:
        """Normalize LLM-generated title before persisting it."""
        normalized = " ".join(title.strip().split())
        normalized = normalized.strip("\"'")
        normalized = normalized.rstrip(".!?;:,")

        if not normalized:
            return ""

        if len(normalized) > self.MAX_TITLE_LENGTH:
            normalized = normalized[: self.MAX_TITLE_LENGTH].rsplit(" ", 1)[0]
            if not normalized:
                normalized = title[: self.MAX_TITLE_LENGTH].strip()

        return normalized

    def _get_structured_title_llm(self) -> Any:
        """Return cached structured-output LLM for title generation."""
        if self._structured_title_llm is None:
            self._structured_title_llm = self._llm_factory().with_structured_output(
                GeneratedConversationTitle
            )
        return self._structured_title_llm

    @staticmethod
    def _default_title_llm_factory() -> Any:
        """Create a small non-streaming model for title generation."""
        return get_chat_azure_openai_legacy(
            temperature=0.2,
            streaming=False,
            max_tokens=32,
        )

    async def get_messages(
        self,
        conversation_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Message]:
        """Get messages for a conversation in chronological order.

        Args:
            conversation_id: ID of the conversation
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of Message instances in chronological order
        """
        return await self.message_repo.get_by_conversation(
            conversation_id=conversation_id,
            skip=skip,
            limit=limit,
        )

    async def get_message(self, message_id: str) -> Optional[Message]:
        """Get a single persisted message by ID."""
        return await self.message_repo.get_by_id(message_id)

    async def get_langchain_messages(
        self,
        conversation_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BaseMessage]:
        """Get messages in LangChain BaseMessage format.

        Converts stored messages to LangChain message types:
        - user -> HumanMessage
        - assistant -> AIMessage
        - system -> SystemMessage
        - tool -> ToolMessage

        Args:
            conversation_id: ID of the conversation
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of LangChain BaseMessage instances

        Requirements: 5.4
        """
        messages = await self.get_messages(
            conversation_id=conversation_id,
            skip=skip,
            limit=limit,
        )
        return [self._to_langchain_message(msg) for msg in messages]

    def _to_langchain_message(self, message: Message) -> BaseMessage:
        """Convert a Message to LangChain BaseMessage format.

        Args:
            message: Message instance to convert

        Returns:
            LangChain BaseMessage instance

        Requirements: 5.4
        """
        role = message.role
        content = message.content

        if role == MessageRole.USER:
            return HumanMessage(content=content)

        if role == MessageRole.ASSISTANT:
            # Include tool_calls if present
            tool_calls = []
            if message.metadata and message.metadata.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "args": tc.arguments,
                    }
                    for tc in message.metadata.tool_calls
                ]
            if tool_calls:
                return AIMessage(content=content, tool_calls=tool_calls)
            return AIMessage(content=content)

        if role == MessageRole.SYSTEM:
            return SystemMessage(content=content)

        if role == MessageRole.TOOL:
            # Tool messages require tool_call_id
            tool_call_id = ""
            if message.metadata and message.metadata.tool_call_id:
                tool_call_id = message.metadata.tool_call_id
            return ToolMessage(content=content, tool_call_id=tool_call_id)

        # Fallback to HumanMessage for unknown roles
        return HumanMessage(content=content)

    async def delete_conversation(
        self,
        conversation_id: str,
        organization_id: Optional[str] = None,
    ) -> bool:
        """Soft delete a conversation and all its messages.

        Args:
            conversation_id: ID of the conversation to delete

        Returns:
            True if conversation was deleted, False otherwise
        """
        # First soft delete all messages in the conversation
        await self.message_repo.soft_delete_by_conversation(conversation_id)

        # Then soft delete the conversation itself
        return await self.conversation_repo.soft_delete(
            conversation_id,
            organization_id=organization_id,
        )

    async def get_conversation(
        self,
        conversation_id: str,
        organization_id: Optional[str] = None,
        has_thread_id: Optional[bool] = None,
    ) -> Optional[StockAgentConversation]:
        """Get a conversation by ID.

        Args:
            conversation_id: ID of the conversation
            has_thread_id: Optional runtime filter based on thread mapping presence

        Returns:
            StockAgentConversation instance if found, None otherwise
        """
        return await self.conversation_repo.get_by_id(
            conversation_id,
            organization_id=organization_id,
            has_thread_id=has_thread_id,
        )

    @staticmethod
    def matches_runtime_class(
        conversation: Optional[StockAgentConversation],
        has_thread_id: Optional[bool] = None,
    ) -> bool:
        """Return True when a conversation matches the expected runtime class."""
        if conversation is None:
            return False

        if has_thread_id is None:
            return True

        return (conversation.thread_id is not None) is has_thread_id

    async def get_user_conversation(
        self,
        conversation_id: str,
        user_id: str,
        organization_id: Optional[str] = None,
        has_thread_id: Optional[bool] = None,
    ) -> Optional[StockAgentConversation]:
        """Get a conversation only when it belongs to the expected user/runtime."""
        conversation = await self.get_conversation(
            conversation_id,
            organization_id=organization_id,
            has_thread_id=has_thread_id,
        )
        if conversation is None or conversation.user_id != user_id:
            return None
        return conversation

    async def get_user_conversations(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
        has_thread_id: Optional[bool] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[StockAgentConversation]:
        """Get conversations for a user with pagination.

        Args:
            user_id: ID of the user
            has_thread_id: Optional runtime filter based on thread mapping presence
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of StockAgentConversation instances
        """
        return await self.conversation_repo.get_by_user(
            user_id=user_id,
            organization_id=organization_id,
            has_thread_id=has_thread_id,
            skip=skip,
            limit=limit,
        )

    async def search_user_conversations(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
        has_thread_id: Optional[bool] = None,
        status: Optional[ConversationStatus] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> StockAgentConversationSearchResult:
        """Search conversations for a user with filters and pagination.

        Args:
            user_id: ID of the user
            has_thread_id: Optional runtime filter based on thread mapping presence
            status: Optional status filter
            search: Optional title search query
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            StockAgentConversationSearchResult with items and total count

        Requirements: 1.1, 1.2, 1.4, 1.5, 1.6
        """
        return await self.conversation_repo.search_by_user(
            user_id=user_id,
            organization_id=organization_id,
            has_thread_id=has_thread_id,
            status=status,
            search=search,
            skip=skip,
            limit=limit,
        )
