"""Service factory functions for application dependencies."""

from functools import lru_cache

from app.common.event_socket import MeetingEvents
from app.common.meeting_note_socket import build_meeting_note_created_payload
from app.common.repo import (
    get_audio_file_repo,
    get_conversation_repo,
    get_image_generation_job_repo,
    get_image_repo,
    get_interview_conversation_repo,
    get_interview_utterance_repo,
    get_lead_agent_skill_repo,
    get_lead_agent_skill_access_repo,
    get_meeting_note_chunk_repo,
    get_meeting_repo,
    get_meeting_utterance_repo,
    get_member_repo,
    get_message_repo,
    get_org_repo,
    get_sheet_connection_repo,
    get_sheet_data_repo,
    get_sheet_sync_state_repo,
    get_stock_symbol_repo,
    get_user_repo,
    get_voice_repo,
)
from app.config.settings import get_settings
from app.domain.models.meeting_note_chunk import MeetingNoteChunk
from app.domain.schemas.meeting import MeetingNoteState
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
from app.services.ai.lead_agent_service import LeadAgentService
from app.services.ai.lead_agent_skill_access_resolver import (
    LeadAgentSkillAccessResolver,
)
from app.services.ai.lead_agent_skill_service import LeadAgentSkillService
from app.services.ai.pipeline_validator import PipelineValidator
from app.services.analytics.analytics_service import AnalyticsService
from app.services.analytics.cache_manager import AnalyticsCacheManager
from app.services.auth.auth_service import AuthService
from app.services.image.image_service import ImageService
from app.services.image.image_generation_service import ImageGenerationService
from app.services.interview.answer_service import InterviewAnswerService
from app.services.meeting.meeting_management_service import (
    MeetingManagementService,
)
from app.services.meeting.meeting_service import MeetingService
from app.services.meeting.note_generation_service import MeetingNoteGenerationService
from app.services.meeting.note_processing_service import MeetingNoteProcessingService
from app.services.meeting.note_state_store import RedisMeetingNoteStateStore
from app.services.meeting.session_manager import MeetingSessionManager
from app.services.organization.organization_service import OrganizationService
from app.services.sheet_crawler.crawler_service import SheetCrawlerService
from app.services.stocks.cache import StockCatalogCache
from app.services.stocks.refresh import StockCatalogSnapshotRefresher
from app.services.stocks.stock_catalog_service import StockCatalogService
from app.services.stocks.vnstock_gateway import VnstockListingGateway
from app.services.stt.context_store import RedisInterviewContextStore
from app.services.stt.interview_session_manager import InterviewSessionManager
from app.services.stt.session_manager import STTSessionManager
from app.services.stt.stt_service import STTService
from app.services.tts.tts_service import TTSService
from app.services.user.user_service import UserService
from app.services.voice.voice_service import VoiceService
from app.socket_gateway.worker_gateway import worker_gateway


@lru_cache
def get_redis_queue() -> RedisQueue:
    """Get singleton RedisQueue instance.

    Returns:
        RedisQueue instance with Redis client
    """
    client = RedisClient.get_client()
    return RedisQueue(client)


@lru_cache
def get_meeting_note_queue() -> RedisQueue:
    """Get singleton RedisQueue instance for meeting note tasks."""
    return get_redis_queue()


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


@lru_cache
def get_stock_catalog_cache() -> StockCatalogCache:
    """Get singleton stock catalog cache helper."""
    client = RedisClient.get_client()
    return StockCatalogCache(client)


@lru_cache
def get_vnstock_listing_gateway() -> VnstockListingGateway:
    """Get singleton vnstock listing gateway."""
    return VnstockListingGateway()


@lru_cache
def get_stock_catalog_refresher() -> StockCatalogSnapshotRefresher:
    """Get singleton stock catalog snapshot refresher."""
    return StockCatalogSnapshotRefresher(
        gateway=get_vnstock_listing_gateway(),
        repository=get_stock_symbol_repo(),
    )


@lru_cache
def get_stock_catalog_service() -> StockCatalogService:
    """Get singleton stock catalog service."""
    return StockCatalogService(
        repository=get_stock_symbol_repo(),
        refresher=get_stock_catalog_refresher(),
        cache=get_stock_catalog_cache(),
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
def get_lead_agent_skill_access_resolver() -> LeadAgentSkillAccessResolver:
    """Get singleton lead-agent skill access resolver instance."""
    return LeadAgentSkillAccessResolver(
        repository=get_lead_agent_skill_access_repo(),
        skill_repository=get_lead_agent_skill_repo(),
    )


@lru_cache
def get_lead_agent_skill_service() -> LeadAgentSkillService:
    """Get singleton lead-agent skill management service instance."""
    return LeadAgentSkillService(
        skill_repository=get_lead_agent_skill_repo(),
        access_repository=get_lead_agent_skill_access_repo(),
    )


def get_lead_agent_service() -> LeadAgentService:
    """Get one LeadAgentService instance."""
    return LeadAgentService(
        conversation_service=get_conversation_service(),
        skill_access_resolver=get_lead_agent_skill_access_resolver(),
    )


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


def get_meeting_deepgram_live_client() -> DeepgramLiveClient:
    """Get a Deepgram client wrapper pinned to the meeting runtime contract."""
    return DeepgramLiveClient.for_meeting()


@lru_cache
def get_meeting_note_state_store() -> RedisMeetingNoteStateStore:
    """Get singleton Redis-backed meeting note state helper."""
    client = RedisClient.get_client()
    return RedisMeetingNoteStateStore(client)


@lru_cache
def get_meeting_note_generation_service() -> MeetingNoteGenerationService:
    """Get singleton AI meeting note generation service."""
    return MeetingNoteGenerationService()


async def _emit_meeting_note_created_chunk(
    chunk: MeetingNoteChunk,
    state: MeetingNoteState,
) -> None:
    """Emit one created note chunk only to the meeting creator."""
    await worker_gateway.emit_to_user(
        user_id=state.created_by_user_id,
        event=MeetingEvents.NOTE_CREATED,
        data=build_meeting_note_created_payload(chunk=chunk),
        organization_id=state.organization_id,
    )


@lru_cache
def get_meeting_note_processing_service() -> MeetingNoteProcessingService:
    """Get singleton worker-side meeting note processing service."""
    return MeetingNoteProcessingService(
        note_state_store=get_meeting_note_state_store(),
        utterance_repo=get_meeting_utterance_repo(),
        note_chunk_repo=get_meeting_note_chunk_repo(),
        note_generation_service=get_meeting_note_generation_service(),
        note_chunk_created_callback=_emit_meeting_note_created_chunk,
    )


@lru_cache
def get_meeting_session_manager() -> MeetingSessionManager:
    """Get singleton meeting session manager instance."""
    settings = get_settings()
    return MeetingSessionManager(
        deepgram_client_factory=get_meeting_deepgram_live_client,
        meeting_repo=get_meeting_repo(),
        meeting_note_queue=get_meeting_note_queue(),
        meeting_note_queue_name=settings.MEETING_NOTE_QUEUE_NAME,
    )


@lru_cache
def get_meeting_service() -> MeetingService:
    """Get singleton meeting transcription service instance."""
    return MeetingService(
        session_manager=get_meeting_session_manager(),
        member_repo=get_member_repo(),
    )


@lru_cache
def get_meeting_management_service() -> MeetingManagementService:
    """Get singleton HTTP meeting management service instance."""
    return MeetingManagementService(
        meeting_repo=get_meeting_repo(),
        utterance_repo=get_meeting_utterance_repo(),
        note_chunk_repo=get_meeting_note_chunk_repo(),
        member_repo=get_member_repo(),
    )


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
    return STTSessionManager(
        deepgram_client_factory=get_deepgram_live_client,
        context_store=get_interview_context_store(),
        utterance_repo=get_interview_utterance_repo(),
        answer_service=get_interview_answer_service(),
    )


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
