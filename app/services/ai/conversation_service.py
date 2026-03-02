"""Conversation service for managing conversations and messages.

Provides business logic for conversation management including:
- Creating conversations with auto-generated titles
- Adding messages with conversation stats updates
- LangChain compatibility for AI integration
"""

from typing import Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.domain.models.conversation import Conversation, ConversationStatus
from app.domain.models.message import (
    Attachment,
    Message,
    MessageMetadata,
    MessageRole,
)
from app.repo.conversation_repo import ConversationRepository, SearchResult
from app.repo.message_repo import MessageRepository


class ConversationService:
    """Service for managing conversations and messages.

    Handles business logic including:
    - Auto title generation for new conversations
    - Updating conversation stats when messages are added
    - Converting messages to LangChain format
    """

    DEFAULT_TITLE = "New Conversation"
    MAX_TITLE_LENGTH = 50

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
    ):
        """Initialize ConversationService with repositories.

        Args:
            conversation_repo: Repository for conversation operations
            message_repo: Repository for message operations
        """
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo

    async def create_conversation(
        self,
        user_id: str,
        title: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation with auto title generation.

        If no title is provided, a default title is assigned.

        Args:
            user_id: ID of the user creating the conversation
            title: Optional title for the conversation

        Returns:
            Created Conversation instance

        Requirements: 4.1
        """
        return await self.conversation_repo.create(
            user_id=user_id,
            title=title,
            organization_id=organization_id,
        )

    async def add_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        organization_id: Optional[str] = None,
        attachments: Optional[list[Attachment]] = None,
        metadata: Optional[MessageMetadata] = None,
        is_complete: bool = True,
    ) -> Message:
        """Add a message to a conversation and update conversation stats.

        Also handles auto title generation for the first user message
        if the conversation has the default title.

        Args:
            conversation_id: ID of the conversation
            role: Role of the message sender
            content: Message content text
            attachments: Optional list of attachments
            metadata: Optional AI metadata
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
            is_complete=is_complete,
        )

        # Update conversation stats (message_count and last_message_at)
        await self.conversation_repo.increment_message_count(
            conversation_id=conversation_id,
            last_message_at=message.created_at,
            organization_id=organization_id,
        )

        # Auto-generate title from first user message if conversation has default title
        if role == MessageRole.USER:
            await self._maybe_update_title_from_message(
                conversation_id,
                content,
                organization_id=organization_id,
            )

        return message

    async def _maybe_update_title_from_message(
        self,
        conversation_id: str,
        content: str,
        organization_id: Optional[str] = None,
    ) -> None:
        """Update conversation title from message content if it has default title.

        Only updates if:
        - Conversation exists and is not deleted
        - Conversation has the default title
        - This is the first user message (message_count == 1)

        Args:
            conversation_id: ID of the conversation
            content: Message content to derive title from

        Requirements: 4.2
        """
        conversation = await self.conversation_repo.get_by_id(
            conversation_id,
            organization_id=organization_id,
        )
        if conversation is None:
            return

        # Only update title if it's the default and this is the first message
        if conversation.title == self.DEFAULT_TITLE and conversation.message_count == 1:
            new_title = self._generate_title_from_content(content)
            await self.conversation_repo.update(
                conversation_id=conversation_id,
                title=new_title,
                organization_id=organization_id,
            )

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
    ) -> Optional[Conversation]:
        """Get a conversation by ID.

        Args:
            conversation_id: ID of the conversation

        Returns:
            Conversation instance if found, None otherwise
        """
        return await self.conversation_repo.get_by_id(
            conversation_id,
            organization_id=organization_id,
        )

    async def get_user_conversations(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Conversation]:
        """Get conversations for a user with pagination.

        Args:
            user_id: ID of the user
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of Conversation instances
        """
        return await self.conversation_repo.get_by_user(
            user_id=user_id,
            organization_id=organization_id,
            skip=skip,
            limit=limit,
        )

    async def search_user_conversations(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> SearchResult:
        """Search conversations for a user with filters and pagination.

        Args:
            user_id: ID of the user
            status: Optional status filter
            search: Optional title search query
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            SearchResult with items and total count

        Requirements: 1.1, 1.2, 1.4, 1.5, 1.6
        """
        return await self.conversation_repo.search_by_user(
            user_id=user_id,
            organization_id=organization_id,
            status=status,
            search=search,
            skip=skip,
            limit=limit,
        )
