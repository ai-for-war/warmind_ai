"""Repository factory functions with singleton pattern."""

from functools import lru_cache

from app.infrastructure.database.mongodb import MongoDB
from app.repo.conversation_repo import ConversationRepository
from app.repo.message_repo import MessageRepository
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.repo.organization_repo import OrganizationRepository
from app.repo.sheet_connection_repo import SheetConnectionRepository
from app.repo.sheet_data_repo import SheetDataRepository
from app.repo.sheet_sync_state_repo import SheetSyncStateRepository
from app.repo.user_repo import UserRepository


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
