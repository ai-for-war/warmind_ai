"""Service factory functions with singleton pattern."""

from functools import lru_cache

from app.common.repo import (
    get_audio_file_repo,
    get_conversation_repo,
    get_image_generation_job_repo,
    get_image_repo,
    get_interview_conversation_repo,
    get_interview_utterance_repo,
    get_member_repo,
    get_message_repo,
    get_org_repo,
    get_sheet_connection_repo,
    get_sheet_data_repo,
    get_sheet_sync_state_repo,
    get_user_repo,
    get_voice_repo,
)
from app.infrastructure.cloudinary.client import CloudinaryClient
from app.infrastructure.deepgram.client import DeepgramLiveClient
from app.infrastructure.google_sheets.client import GoogleSheetClient
from app.infrastructure.minimax.client import MiniMaxClient
from app.infrastructure.minimax.image_client import MiniMaxImageClient
from app.infrastructure.redis.client import RedisClient
from app.infrastructure.redis.redis_queue import RedisQueue
from app.services.ai.chat_service import ChatService
from app.services.ai.conversation_service import ConversationService
from app.services.ai.data_query_service import DataQueryService
from app.services.ai.pipeline_validator import PipelineValidator
from app.services.analytics.analytics_service import AnalyticsService
from app.services.analytics.cache_manager import AnalyticsCacheManager
from app.services.auth.auth_service import AuthService
from app.services.image.image_service import ImageService
from app.services.image.image_generation_service import ImageGenerationService
from app.services.interview.answer_service import InterviewAnswerService
from app.services.organization.organization_service import OrganizationService
from app.services.sheet_crawler.crawler_service import SheetCrawlerService
from app.services.stt.context_store import RedisInterviewContextStore
from app.services.stt.interview_session_manager import InterviewSessionManager
from app.services.stt.session_manager import STTSessionManager
from app.services.stt.stt_service import STTService
from app.services.user.user_service import UserService
from app.services.tts.tts_service import TTSService
from app.services.voice.voice_service import VoiceService


@lru_cache
def get_redis_queue() -> RedisQueue:
    """Get singleton RedisQueue instance.

    Returns:
        RedisQueue instance with Redis client
    """
    client = RedisClient.get_client()
    return RedisQueue(client)


@lru_cache
def get_auth_service() -> AuthService:
    """Get singleton AuthService instance.

    Returns:
        AuthService instance with UserRepository
    """
    user_repo = get_user_repo()
    return AuthService(user_repo)


@lru_cache
def get_org_service() -> OrganizationService:
    """Get singleton OrganizationService instance.

    Returns:
        OrganizationService instance with repositories
    """
    return OrganizationService(
        organization_repo=get_org_repo(),
        member_repo=get_member_repo(),
        user_repo=get_user_repo(),
    )


@lru_cache
def get_user_service() -> UserService:
    """Get singleton UserService instance.

    Returns:
        UserService instance with repositories
    """
    return UserService(
        user_repo=get_user_repo(),
        organization_repo=get_org_repo(),
        member_repo=get_member_repo(),
    )


@lru_cache
def get_google_sheet_client() -> GoogleSheetClient:
    """Get singleton GoogleSheetClient instance.

    Returns:
        GoogleSheetClient instance for Google Sheets API access
    """
    return GoogleSheetClient()


@lru_cache
def get_analytics_cache_manager() -> AnalyticsCacheManager:
    """Get singleton AnalyticsCacheManager instance.

    Returns:
        AnalyticsCacheManager instance with Redis client
    """
    client = RedisClient.get_client()
    return AnalyticsCacheManager(client)


@lru_cache
def get_crawler_service() -> SheetCrawlerService:
    """Get singleton SheetCrawlerService instance.

    Returns:
        SheetCrawlerService instance with all dependencies
    """
    return SheetCrawlerService(
        sheet_client=get_google_sheet_client(),
        connection_repo=get_sheet_connection_repo(),
        sync_state_repo=get_sheet_sync_state_repo(),
        data_repo=get_sheet_data_repo(),
        cache_manager=get_analytics_cache_manager(),
    )


@lru_cache
def get_conversation_service() -> ConversationService:
    """Get singleton ConversationService instance.

    Returns:
        ConversationService instance with repositories
    """
    conversation_repo = get_conversation_repo()
    message_repo = get_message_repo()
    return ConversationService(conversation_repo, message_repo)


@lru_cache
def get_analytics_service() -> AnalyticsService:
    """Get singleton AnalyticsService instance.

    Returns:
        AnalyticsService instance with all dependencies
    """
    return AnalyticsService(
        connection_repo=get_sheet_connection_repo(),
        data_repo=get_sheet_data_repo(),
        cache_manager=get_analytics_cache_manager(),
    )


def get_chat_service() -> ChatService:
    """Get ChatService instance.

    Note: Not using @lru_cache because ChatService depends on
    DataQueryService which may need fresh connections.

    Returns:
        ChatService instance with all dependencies
    """
    conversation_service = get_conversation_service()
    data_query_service = get_data_query_service()
    return ChatService(conversation_service, data_query_service)


@lru_cache
def get_pipeline_validator() -> PipelineValidator:
    """Get singleton PipelineValidator instance.

    Returns:
        PipelineValidator instance for validating aggregation pipelines
    """
    return PipelineValidator()


@lru_cache
def get_data_query_service() -> DataQueryService:
    """Get singleton DataQueryService instance.

    Returns:
        DataQueryService instance with all dependencies
    """
    return DataQueryService(
        connection_repo=get_sheet_connection_repo(),
        data_repo=get_sheet_data_repo(),
        pipeline_validator=get_pipeline_validator(),
    )


@lru_cache
def get_cloudinary_client() -> CloudinaryClient:
    """Get singleton CloudinaryClient instance."""
    return CloudinaryClient()


@lru_cache
def get_image_service() -> ImageService:
    """Get singleton ImageService instance."""
    return ImageService(
        image_repo=get_image_repo(),
        cloudinary_client=get_cloudinary_client(),
    )


@lru_cache
def get_minimax_client() -> MiniMaxClient:
    """Get singleton MiniMaxClient instance."""
    return MiniMaxClient()


def get_deepgram_live_client() -> DeepgramLiveClient:
    """Get a Deepgram live client wrapper instance.

    A new wrapper is returned per call so each STT session can own an isolated
    provider connection lifecycle.
    """
    return DeepgramLiveClient()


@lru_cache
def get_interview_context_store() -> RedisInterviewContextStore:
    """Get singleton Redis-backed interview context store instance."""
    client = RedisClient.get_client()
    return RedisInterviewContextStore(client)


@lru_cache
def get_interview_answer_service() -> InterviewAnswerService:
    """Get singleton interview answer service instance."""
    return InterviewAnswerService(
        context_store=get_interview_context_store(),
        conversation_repo=get_interview_conversation_repo(),
        utterance_repo=get_interview_utterance_repo(),
    )


@lru_cache
def get_interview_session_manager() -> InterviewSessionManager:
    """Get singleton interview session manager instance."""
    return InterviewSessionManager(
        deepgram_client_factory=get_deepgram_live_client,
        context_store=get_interview_context_store(),
        conversation_repo=get_interview_conversation_repo(),
        utterance_repo=get_interview_utterance_repo(),
        answer_service=get_interview_answer_service(),
    )


@lru_cache
def get_stt_session_manager() -> STTSessionManager:
    """Get singleton STT session manager instance."""
    return STTSessionManager(deepgram_client_factory=get_deepgram_live_client)


@lru_cache
def get_stt_service() -> STTService:
    """Get singleton STT service instance."""
    return STTService(session_manager=get_stt_session_manager())


@lru_cache
def get_voice_service() -> VoiceService:
    """Get singleton VoiceService instance."""
    return VoiceService(
        voice_repo=get_voice_repo(),
        cloudinary_client=get_cloudinary_client(),
        minimax_client=get_minimax_client(),
    )


@lru_cache
def get_tts_service() -> TTSService:
    """Get singleton TTSService instance."""
    return TTSService(
        audio_file_repo=get_audio_file_repo(),
        voice_repo=get_voice_repo(),
        cloudinary_client=get_cloudinary_client(),
        minimax_client=get_minimax_client(),
    )


@lru_cache
def get_minimax_image_client() -> MiniMaxImageClient:
    """Get singleton MiniMax image client instance."""
    return MiniMaxImageClient()


@lru_cache
def get_image_generation_service() -> ImageGenerationService:
    """Get singleton image generation service instance."""
    return ImageGenerationService(
        image_generation_job_repo=get_image_generation_job_repo(),
        redis_queue=get_redis_queue(),
        image_repo=get_image_repo(),
        cloudinary_client=get_cloudinary_client(),
    )
