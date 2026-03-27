"""Lead-agent service for thread-native agent execution."""

from typing import Any
from uuid import UUID, uuid4

from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.lead_agent.agent import create_lead_agent
from app.common.exceptions.ai_exceptions import (
    InvalidLeadAgentThreadError,
    LeadAgentRunError,
    LeadAgentThreadNotFoundError,
)
from app.common.exceptions import AppException


class LeadAgentService:
    """Manage lead-agent threads backed by LangGraph checkpoints."""

    def __init__(self) -> None:
        """Initialize the service with lazy agent creation."""
        self._agent: CompiledStateGraph | None = None

    @property
    def agent(self) -> CompiledStateGraph:
        """Return the cached lead-agent runtime."""
        if self._agent is None:
            self._agent = create_lead_agent()
        return self._agent

    async def create_thread(
        self,
        user_id: str,
        organization_id: str | None = None,
    ) -> str:
        """Create a new lead-agent thread and seed caller scope into state."""
        thread_id = str(uuid4())
        config = self._thread_config(thread_id)
        initial_state = {
            "messages": [],
            "user_id": user_id,
            "organization_id": organization_id,
        }

        # LangChain create_agent graphs bootstrap from __start__, not __input__.
        # Seeding through __start__ persists custom state channels like user scope.
        await self.agent.aupdate_state(
            config,
            values=initial_state,
            as_node="__start__",
        )
        return thread_id

    async def run_thread(
        self,
        thread_id: str,
        user_id: str,
        content: str,
        organization_id: str | None = None,
    ) -> str:
        """Invoke an existing lead-agent thread with new user input."""
        normalized_thread_id = self._normalize_thread_id(thread_id)
        normalized_content = content.strip()
        if not normalized_content:
            raise AppException("Content is required")

        state = await self._get_thread_state(normalized_thread_id)
        self._validate_thread_scope(
            state,
            user_id=user_id,
            organization_id=organization_id,
        )

        result = await self.agent.ainvoke(
            {
                "messages": [{"role": "user", "content": normalized_content}],
                "user_id": user_id,
                "organization_id": organization_id,
            },
            config=self._thread_config(normalized_thread_id),
        )

        return self._extract_final_response(result)

    async def _get_thread_state(self, thread_id: str) -> dict[str, Any]:
        """Load the latest checkpointed state for a thread."""
        snapshot = await self.agent.aget_state(self._thread_config(thread_id))
        values = getattr(snapshot, "values", None)
        if not values:
            raise LeadAgentThreadNotFoundError()

        state = dict(values)
        if not state.get("user_id"):
            raise LeadAgentThreadNotFoundError()

        return state

    def _validate_thread_scope(
        self,
        state: dict[str, Any],
        user_id: str,
        organization_id: str | None,
    ) -> None:
        """Ensure the checkpointed thread belongs to the authenticated caller."""
        if state.get("user_id") != user_id:
            raise LeadAgentThreadNotFoundError()

        if state.get("organization_id") != organization_id:
            raise LeadAgentThreadNotFoundError()

    @staticmethod
    def _thread_config(thread_id: str) -> dict[str, dict[str, str]]:
        """Build LangGraph config for a thread."""
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _normalize_thread_id(thread_id: str) -> str:
        """Validate and normalize a thread identifier."""
        try:
            return str(UUID(thread_id))
        except ValueError as exc:
            raise InvalidLeadAgentThreadError() from exc

    def _extract_final_response(self, result: dict[str, Any]) -> str:
        """Extract the final assistant response from an agent run result."""
        messages = result.get("messages") if isinstance(result, dict) else None
        if not messages:
            raise LeadAgentRunError()

        for message in reversed(messages):
            if self._is_assistant_message(message):
                response = self._message_content_to_text(message)
                if response:
                    return response

        fallback_response = self._message_content_to_text(messages[-1])
        if fallback_response:
            return fallback_response

        raise LeadAgentRunError()

    @staticmethod
    def _is_assistant_message(message: Any) -> bool:
        """Return True when a message is an assistant/AI message."""
        if isinstance(message, dict):
            return message.get("role") == "assistant"

        if getattr(message, "type", None) == "ai":
            return True

        if getattr(message, "role", None) == "assistant":
            return True

        return message.__class__.__name__ == "AIMessage"

    @classmethod
    def _message_content_to_text(cls, message: Any) -> str:
        """Normalize message content into a plain-text response."""
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)

        return cls._content_to_text(content).strip()

    @classmethod
    def _content_to_text(cls, content: Any) -> str:
        """Convert structured message content into text."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = [cls._content_to_text(item).strip() for item in content]
            return "\n".join(part for part in parts if part)

        if isinstance(content, dict):
            if "text" in content and content["text"] is not None:
                return str(content["text"])
            if "content" in content:
                return cls._content_to_text(content["content"])
            return ""

        if content is None:
            return ""

        return str(content)
