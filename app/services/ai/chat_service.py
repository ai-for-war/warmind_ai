"""Chat service for handling chat messages and AI agent responses.

Provides business logic for:
- Sending user messages and creating conversations
- Processing agent responses with streaming via Socket.IO
- Managing conversation history for AI context
- Routing to appropriate handlers via ChatWorkflow
"""

import logging
from typing import Optional

from app.common.event_socket import ChatEvents
from app.domain.models.conversation import ConversationStatus
from app.domain.models.message import MessageMetadata, MessageRole
from app.graphs.registry import get_chat_workflow
from app.repo.conversation_repo import SearchResult
from app.services.ai.conversation_service import ConversationService
from app.services.ai.data_query_service import DataQueryService
from app.socket_gateway import gateway

logger = logging.getLogger(__name__)


class ChatService:
    """Service for managing chat messages and AI agent responses.

    Handles:
    - Saving user messages to conversations
    - Creating new conversations when needed
    - Processing agent responses with ChatWorkflow
    - Emitting socket events for real-time updates

    Requirements: 10.1, 10.2, 10.3, 10.4, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
    """

    def __init__(
        self,
        conversation_service: ConversationService,
        data_query_service: DataQueryService,
    ):
        """Initialize ChatService with dependencies.

        Args:
            conversation_service: Service for conversation/message operations
            data_query_service: Service for querying user's sheet data
        """
        self.conversation_service = conversation_service
        self.data_query_service = data_query_service

    async def send_message(
        self,
        user_id: str,
        content: str,
        conversation_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """Save user message and return message_id and conversation_id.

        If conversation_id is not provided, creates a new conversation.

        Args:
            user_id: ID of the user sending the message
            content: Message content text
            conversation_id: Optional existing conversation ID

        Returns:
            Tuple of (user_message_id, conversation_id)

        Requirements: 1.2, 1.3, 1.4
        """
        # Create new conversation if not provided
        if conversation_id is None:
            conversation = await self.conversation_service.create_conversation(
                user_id=user_id,
                organization_id=organization_id,
            )
            conversation_id = conversation.id

        # Save user message to database
        message = await self.conversation_service.add_message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=content,
            organization_id=organization_id,
        )

        return message.id, conversation_id

    async def search_conversations(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> SearchResult:
        """Search conversations for a user with filters.

        Delegates to conversation_service which uses the repository.

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
        return await self.conversation_service.search_user_conversations(
            user_id=user_id,
            organization_id=organization_id,
            status=status,
            search=search,
            skip=skip,
            limit=limit,
        )

    async def process_agent_response(
        self,
        user_id: str,
        conversation_id: str,
        organization_id: Optional[str] = None,
    ) -> None:
        """Process agent response using ChatWorkflow and stream via socket events.

        This method is designed to run as a background task.
        It loads conversation history and user connections, runs the ChatWorkflow.
        Token streaming and tool events are emitted directly from workflow nodes.

        The workflow:
        1. Emit MESSAGE_STARTED event
        2. Load user's sheet connections for data queries
        3. Load conversation history as LangChain messages
        4. Run ChatWorkflow (nodes emit token/tool events directly)
        5. Save assistant response to database
        6. Emit MESSAGE_COMPLETED or MESSAGE_FAILED event

        Args:
            user_id: ID of the user (for socket room targeting)
            conversation_id: ID of the conversation to process

        Requirements: 10.1, 10.2, 10.3, 10.4, 11.1, 11.5, 11.6
        """
        try:
            # Emit MESSAGE_STARTED event
            await gateway.emit_to_user(
                user_id=user_id,
                event=ChatEvents.MESSAGE_STARTED,
                data={"conversation_id": conversation_id},
            )

            # Load user's sheet connections with schemas
            user_connections = await self.data_query_service.get_user_connections(
                user_id=user_id,
                organization_id=organization_id,
            )

            # Load conversation history as LangChain messages
            messages = await self.conversation_service.get_langchain_messages(
                conversation_id=conversation_id,
            )

            # Create ChatWorkflow from registry
            graph = get_chat_workflow(user_connections=user_connections)

            # Prepare initial state
            initial_state = {
                "messages": messages,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "user_connections": user_connections,
                "tool_calls": [],
            }

            # Run workflow - nodes emit Socket.IO events directly
            result = await graph.ainvoke(initial_state)

            # Get response from workflow result
            response_content = result.get("agent_response", "")

            # Save assistant message to database
            assistant_message = await self.conversation_service.add_message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=response_content,
                organization_id=organization_id,
                metadata=MessageMetadata(),
            )

            # Emit MESSAGE_COMPLETED event
            await gateway.emit_to_user(
                user_id=user_id,
                event=ChatEvents.MESSAGE_COMPLETED,
                data={
                    "conversation_id": conversation_id,
                    "message_id": assistant_message.id,
                    "content": response_content,
                    "metadata": None,
                },
            )

        except Exception as e:
            logger.exception(
                "Error processing agent response for conversation %s",
                conversation_id,
            )
            # Emit MESSAGE_FAILED event
            await gateway.emit_to_user(
                user_id=user_id,
                event=ChatEvents.MESSAGE_FAILED,
                data={
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )
