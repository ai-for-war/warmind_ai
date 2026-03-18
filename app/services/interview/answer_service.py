"""Interview answer service for Redis-first context assembly and AI generation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.common.event_socket import InterviewEvents
from app.common.exceptions import InterviewAITriggerError, RedisContextReadError
from app.domain.models.interview_utterance import InterviewUtterance
from app.domain.schemas.stt import (
    InterviewAnswerFailedPayload,
    InterviewAnswerPayload,
    InterviewAnswerStartedPayload,
    InterviewAnswerTokenPayload,
)
from app.infrastructure.llm.factory import get_chat_openai_legacy
from app.prompts.system.interview_answer import INTERVIEW_ANSWER_SYSTEM_PROMPT
from app.repo.interview_conversation_repo import InterviewConversationRepository
from app.repo.interview_utterance_repo import InterviewUtteranceRepository
from app.socket_gateway import gateway
from app.services.stt.context_store import (
    RedisInterviewContextStore,
    StableInterviewContextUtterance,
)


class InterviewAnswerService:
    """Build recent interview context and generate text-only AI answers."""

    def __init__(
        self,
        *,
        context_store: RedisInterviewContextStore,
        conversation_repo: InterviewConversationRepository,
        utterance_repo: InterviewUtteranceRepository,
        llm_factory: Callable[[], Any] | None = None,
        max_context_utterances: int = 10,
    ) -> None:
        self.context_store = context_store
        self.conversation_repo = conversation_repo
        self.utterance_repo = utterance_repo
        self._llm_factory = llm_factory or self._default_llm_factory
        self._llm: Any | None = None
        self.max_context_utterances = max(max_context_utterances, 1)

    async def build_context_window(
        self,
        *,
        conversation_id: str,
        just_closed_utterance: StableInterviewContextUtterance,
        limit: int | None = None,
    ) -> list[StableInterviewContextUtterance]:
        """Load a recent stable interview context window in timeline order."""
        requested_limit = limit or self.max_context_utterances

        try:
            recent_utterances = await self.context_store.get_recent_utterances(
                conversation_id=conversation_id,
                limit=requested_limit,
            )
        except RedisContextReadError as exc:
            raise InterviewAITriggerError(
                "Failed to load recent stable interview context from Redis"
            ) from exc

        merged = {
            utterance.utterance_id: utterance
            for utterance in recent_utterances
            if utterance.source in {"interviewer", "user"}
        }

        if just_closed_utterance.utterance_id not in merged:
            fallback_utterances = await self._load_fallback_utterances(
                conversation_id=conversation_id,
                limit=requested_limit,
            )
            for utterance in fallback_utterances:
                merged.setdefault(utterance.utterance_id, utterance)

        merged[just_closed_utterance.utterance_id] = just_closed_utterance
        ordered = sorted(
            merged.values(),
            key=lambda utterance: (
                utterance.turn_closed_at,
                utterance.ended_at,
                utterance.started_at,
                utterance.utterance_id,
            ),
        )
        return ordered[-requested_limit:]

    async def stream_for_closed_utterance(
        self,
        *,
        user_id: str,
        organization_id: str | None,
        closed_utterance: StableInterviewContextUtterance,
    ) -> InterviewAnswerPayload | None:
        """Stream an interview answer only for a closed interviewer utterance."""
        if closed_utterance.source != "interviewer":
            return None

        context_window = await self.build_context_window(
            conversation_id=closed_utterance.conversation_id,
            just_closed_utterance=closed_utterance,
        )
        prompt = self._build_user_prompt(
            context_window=context_window,
            closed_utterance=closed_utterance,
        )

        try:
            await gateway.emit_to_user(
                user_id=user_id,
                event=InterviewEvents.ANSWER_STARTED,
                data=InterviewAnswerStartedPayload(
                    conversation_id=closed_utterance.conversation_id,
                    utterance_id=closed_utterance.utterance_id,
                ).model_dump(exclude_none=True, by_alias=True),
                organization_id=organization_id,
            )

            full_content = ""
            async for chunk in self._get_llm().astream(
                [
                    SystemMessage(content=INTERVIEW_ANSWER_SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ]
            ):
                token = self._extract_stream_token(getattr(chunk, "content", ""))
                if not token:
                    continue
                full_content += token
                await gateway.emit_to_user(
                    user_id=user_id,
                    event=InterviewEvents.ANSWER_TOKEN,
                    data=InterviewAnswerTokenPayload(
                        conversation_id=closed_utterance.conversation_id,
                        utterance_id=closed_utterance.utterance_id,
                        token=token,
                    ).model_dump(exclude_none=True, by_alias=True),
                    organization_id=organization_id,
                )
        except Exception as exc:
            message = "Failed to generate an interview answer"
            await gateway.emit_to_user(
                user_id=user_id,
                event=InterviewEvents.ANSWER_FAILED,
                data=InterviewAnswerFailedPayload(
                    conversation_id=closed_utterance.conversation_id,
                    utterance_id=closed_utterance.utterance_id,
                    error=message,
                ).model_dump(exclude_none=True, by_alias=True),
                organization_id=organization_id,
            )
            raise InterviewAITriggerError(message) from exc

        answer_text = full_content.strip()
        if not answer_text:
            message = "Interview AI returned an empty answer"
            await gateway.emit_to_user(
                user_id=user_id,
                event=InterviewEvents.ANSWER_FAILED,
                data=InterviewAnswerFailedPayload(
                    conversation_id=closed_utterance.conversation_id,
                    utterance_id=closed_utterance.utterance_id,
                    error=message,
                ).model_dump(exclude_none=True, by_alias=True),
                organization_id=organization_id,
            )
            raise InterviewAITriggerError(message)

        payload = InterviewAnswerPayload(
            conversation_id=closed_utterance.conversation_id,
            utterance_id=closed_utterance.utterance_id,
            text=answer_text,
        )
        await gateway.emit_to_user(
            user_id=user_id,
            event=InterviewEvents.ANSWER_COMPLETED,
            data=payload.model_dump(exclude_none=True, by_alias=True),
            organization_id=organization_id,
        )
        await gateway.emit_to_user(
            user_id=user_id,
            event=InterviewEvents.ANSWER,
            data=payload.model_dump(exclude_none=True, by_alias=True),
            organization_id=organization_id,
        )
        return payload

    async def _load_fallback_utterances(
        self,
        *,
        conversation_id: str,
        limit: int,
    ) -> list[StableInterviewContextUtterance]:
        try:
            durable_utterances = (
                await self.utterance_repo.get_recent_durable_by_conversation(
                    conversation_id=conversation_id,
                    limit=limit,
                )
            )
        except Exception:
            return []

        return [
            self._from_durable_utterance(utterance)
            for utterance in durable_utterances
            if utterance.source in {"interviewer", "user"}
        ]

    @staticmethod
    def _from_durable_utterance(
        utterance: InterviewUtterance,
    ) -> StableInterviewContextUtterance:
        return StableInterviewContextUtterance(
            utterance_id=utterance.id,
            conversation_id=utterance.conversation_id,
            source=utterance.source,
            channel=utterance.channel,
            text=utterance.text,
            started_at=utterance.started_at,
            ended_at=utterance.ended_at,
            turn_closed_at=utterance.turn_closed_at,
        )

    @staticmethod
    def _build_user_prompt(
        *,
        context_window: list[StableInterviewContextUtterance],
        closed_utterance: StableInterviewContextUtterance,
    ) -> str:
        lines = []
        for utterance in context_window:
            lines.append(f"{utterance.source.upper()}: {utterance.text}")

        transcript = "\n".join(lines) if lines else closed_utterance.text
        return (
            "Recent stable interview transcript:\n"
            f"{transcript}\n\n"
            "Latest interviewer utterance:\n"
            f"{closed_utterance.text}\n\n"
        )

    @staticmethod
    def _normalize_llm_content(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item.strip())
                    continue
                text = getattr(item, "text", None)
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            return "\n".join(part for part in parts if part).strip()
        return str(content).strip()

    @staticmethod
    def _extract_stream_token(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)
        return str(content)

    def _get_llm(self) -> Any:
        """Create the LLM client lazily once per service instance."""
        if self._llm is None:
            self._llm = self._llm_factory()
        return self._llm

    @staticmethod
    def _default_llm_factory() -> Any:
        return get_chat_openai_legacy(
            model="gpt-4.1",
            temperature=0.5,
            streaming=True,
            max_tokens=1024,
        )
