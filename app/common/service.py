"""Service factory functions with singleton pattern."""

from functools import lru_cache

from app.common.repo import (
    get_conversation_repo,
    get_member_repo,
    get_message_repo,
    get_org_repo,
    get_sheet_connection_repo,
    get_sheet_data_repo,
    get_sheet_sync_state_repo,
    get_user_repo,
)
from app.infrastructure.google_sheets.client import GoogleSheetClient
from app.infrastructure.redis.client import RedisClient
from app.infrastructure.redis.redis_queue import RedisQueue
from app.services.ai.chat_service import ChatService
from app.services.ai.conversation_service import ConversationService
from app.services.ai.data_query_service import DataQueryService
from app.services.ai.pipeline_validator import PipelineValidator
from app.services.analytics.analytics_service import AnalyticsService
from app.services.analytics.cache_manager import AnalyticsCacheManager
from app.services.auth.auth_service import AuthService
from app.services.organization.organization_service import OrganizationService
from app.services.sheet_crawler.crawler_service import SheetCrawlerService
from app.services.user.user_service import UserService


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
