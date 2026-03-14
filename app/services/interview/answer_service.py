"""Interview answer service scaffold."""

from app.repo.interview_conversation_repo import InterviewConversationRepository
from app.repo.interview_utterance_repo import InterviewUtteranceRepository
from app.services.stt.context_store import RedisInterviewContextStore


class InterviewAnswerService:
    """Coordinates interview answer generation dependencies."""

    def __init__(
        self,
        *,
        context_store: RedisInterviewContextStore,
        conversation_repo: InterviewConversationRepository,
        utterance_repo: InterviewUtteranceRepository,
    ) -> None:
        self.context_store = context_store
        self.conversation_repo = conversation_repo
        self.utterance_repo = utterance_repo
