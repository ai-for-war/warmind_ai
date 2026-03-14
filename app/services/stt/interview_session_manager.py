"""Interview session manager scaffold for multichannel STT flows."""

from __future__ import annotations

from collections.abc import Callable

from app.infrastructure.deepgram.client import DeepgramLiveClient
from app.repo.interview_conversation_repo import InterviewConversationRepository
from app.repo.interview_utterance_repo import InterviewUtteranceRepository
from app.services.interview.answer_service import InterviewAnswerService
from app.services.stt.context_store import RedisInterviewContextStore


class InterviewSessionManager:
    """Owns shared dependencies for conversation-scoped interview sessions."""

    def __init__(
        self,
        *,
        deepgram_client_factory: Callable[[], DeepgramLiveClient],
        context_store: RedisInterviewContextStore,
        conversation_repo: InterviewConversationRepository,
        utterance_repo: InterviewUtteranceRepository,
        answer_service: InterviewAnswerService,
    ) -> None:
        self._deepgram_client_factory = deepgram_client_factory
        self.context_store = context_store
        self.conversation_repo = conversation_repo
        self.utterance_repo = utterance_repo
        self.answer_service = answer_service

    def create_provider_client(self) -> DeepgramLiveClient:
        """Create an isolated Deepgram client for an interview session."""
        return self._deepgram_client_factory()
