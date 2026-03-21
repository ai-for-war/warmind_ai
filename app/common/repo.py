"""Repository factory functions with singleton pattern."""

from functools import lru_cache

from app.infrastructure.database.mongodb import MongoDB
from app.repo.audio_file_repo import AudioFileRepository
from app.repo.conversation_repo import ConversationRepository
from app.repo.image_generation_job_repo import ImageGenerationJobRepository
from app.repo.image_repo import ImageRepository
from app.repo.interview_conversation_repo import InterviewConversationRepository
from app.repo.interview_utterance_repo import InterviewUtteranceRepository
from app.repo.meeting_repo import MeetingRepository
from app.repo.meeting_utterance_repo import MeetingUtteranceRepository
from app.repo.message_repo import MessageRepository
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.repo.organization_repo import OrganizationRepository
from app.repo.sheet_connection_repo import SheetConnectionRepository
from app.repo.sheet_data_repo import SheetDataRepository
from app.repo.sheet_sync_state_repo import SheetSyncStateRepository
from app.repo.user_repo import UserRepository
from app.repo.voice_repo import VoiceRepository


@lru_cache
def get_user_repo() -> UserRepository:
    """Get singleton UserRepository instance.

    Returns:
        UserRepository instance with database connection
    """
    db = MongoDB.get_db()
    return UserRepository(db)


@lru_cache
def get_org_repo() -> OrganizationRepository:
    """Get singleton OrganizationRepository instance.

    Returns:
        OrganizationRepository instance with database connection
    """
    db = MongoDB.get_db()
    return OrganizationRepository(db)


@lru_cache
def get_member_repo() -> OrganizationMemberRepository:
    """Get singleton OrganizationMemberRepository instance.

    Returns:
        OrganizationMemberRepository instance with database connection
    """
    db = MongoDB.get_db()
    return OrganizationMemberRepository(db)


@lru_cache
def get_sheet_connection_repo() -> SheetConnectionRepository:
    """Get singleton SheetConnectionRepository instance.

    Returns:
        SheetConnectionRepository instance with database connection
    """
    db = MongoDB.get_db()
    return SheetConnectionRepository(db)


@lru_cache
def get_sheet_sync_state_repo() -> SheetSyncStateRepository:
    """Get singleton SheetSyncStateRepository instance.

    Returns:
        SheetSyncStateRepository instance with database connection
    """
    db = MongoDB.get_db()
    return SheetSyncStateRepository(db)


@lru_cache
def get_sheet_data_repo() -> SheetDataRepository:
    """Get singleton SheetDataRepository instance.

    Returns:
        SheetDataRepository instance with database connection
    """
    db = MongoDB.get_db()
    return SheetDataRepository(db)


@lru_cache
def get_conversation_repo() -> ConversationRepository:
    """Get singleton ConversationRepository instance.

    Returns:
        ConversationRepository instance with database connection
    """
    db = MongoDB.get_db()
    return ConversationRepository(db)


@lru_cache
def get_message_repo() -> MessageRepository:
    """Get singleton MessageRepository instance.

    Returns:
        MessageRepository instance with database connection
    """
    db = MongoDB.get_db()
    return MessageRepository(db)


@lru_cache
def get_image_repo() -> ImageRepository:
    """Get singleton ImageRepository instance.

    Returns:
        ImageRepository instance with database connection
    """
    db = MongoDB.get_db()
    return ImageRepository(db)


@lru_cache
def get_voice_repo() -> VoiceRepository:
    """Get singleton VoiceRepository instance.

    Returns:
        VoiceRepository instance with database connection
    """
    db = MongoDB.get_db()
    return VoiceRepository(db)


@lru_cache
def get_audio_file_repo() -> AudioFileRepository:
    """Get singleton AudioFileRepository instance.

    Returns:
        AudioFileRepository instance with database connection
    """
    db = MongoDB.get_db()
    return AudioFileRepository(db)


@lru_cache
def get_image_generation_job_repo() -> ImageGenerationJobRepository:
    """Get singleton image generation job repository instance."""
    db = MongoDB.get_db()
    return ImageGenerationJobRepository(db)


@lru_cache
def get_interview_conversation_repo() -> InterviewConversationRepository:
    """Get singleton interview conversation repository instance."""
    db = MongoDB.get_db()
    return InterviewConversationRepository(db)


@lru_cache
def get_interview_utterance_repo() -> InterviewUtteranceRepository:
    """Get singleton interview utterance repository instance."""
    db = MongoDB.get_db()
    return InterviewUtteranceRepository(db)


@lru_cache
def get_meeting_repo() -> MeetingRepository:
    """Get singleton meeting repository instance."""
    db = MongoDB.get_db()
    return MeetingRepository(db)


@lru_cache
def get_meeting_utterance_repo() -> MeetingUtteranceRepository:
    """Get singleton meeting utterance repository instance."""
    db = MongoDB.get_db()
    return MeetingUtteranceRepository(db)
