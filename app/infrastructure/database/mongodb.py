"""MongoDB async client using motor."""

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)


class MongoDB:
    """MongoDB connection manager."""

    client: AsyncIOMotorClient
    db: AsyncIOMotorDatabase

    @classmethod
    async def connect(cls, uri: str, db_name: str) -> None:
        """Connect to MongoDB.

        Args:
            uri: MongoDB connection URI
            db_name: Database name to use
        """
        cls.client = AsyncIOMotorClient(uri)
        cls.db = cls.client[db_name]

    @classmethod
    async def disconnect(cls) -> None:
        """Disconnect from MongoDB."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        """Get database instance.

        Returns:
            AsyncIOMotorDatabase instance

        Raises:
            RuntimeError: If not connected to database
        """
        if cls.db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return cls.db

    @classmethod
    async def create_indexes(cls) -> None:
        """Create indexes for all collections.

        Creates compound indexes for efficient querying:
        - organizations: slug (unique), is_active
        - organization_members: (user_id, organization_id) unique, organization_id,
          user_id
        - conversations: (user_id, organization_id, deleted_at, updated_at DESC)
          for user listing in organization scope
        - sheet_connections: (user_id, organization_id), (sync_enabled, organization_id)
          for organization-scoped queries
        - messages: (conversation_id, deleted_at, created_at) for message retrieval

        This method is idempotent - calling it multiple times is safe.
        MongoDB will skip index creation if the index already exists.

        Requirements: 1.2, 1.6, 2.2
        """
        if cls.db is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        # Indexes for organizations collection
        await cls.db.organizations.create_index(
            [("slug", ASCENDING)],
            name="idx_organizations_slug_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_organizations_slug_unique")

        await cls.db.organizations.create_index(
            [("is_active", ASCENDING)],
            name="idx_organizations_is_active",
            background=True,
        )
        logger.info("Created index: idx_organizations_is_active")

        # Indexes for organization_members collection
        await cls.db.organization_members.create_index(
            [("user_id", ASCENDING), ("organization_id", ASCENDING)],
            name="idx_org_members_user_org_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_org_members_user_org_unique")

        await cls.db.organization_members.create_index(
            [("organization_id", ASCENDING)],
            name="idx_org_members_organization_id",
            background=True,
        )
        logger.info("Created index: idx_org_members_organization_id")

        await cls.db.organization_members.create_index(
            [("user_id", ASCENDING)],
            name="idx_org_members_user_id",
            background=True,
        )
        logger.info("Created index: idx_org_members_user_id")

        # Index for conversations collection
        # Supports: get_by_user() with pagination ordered by updated_at DESC
        # Requirements: 1.2 (retrieve by user_id), 1.6 (order by updated_at)
        await cls.db.conversations.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("deleted_at", ASCENDING),
                ("updated_at", DESCENDING),
            ],
            name="idx_conversations_user_org_deleted_updated",
            background=True,
        )
        logger.info("Created index: idx_conversations_user_org_deleted_updated")

        # Indexes for sheet_connections collection
        await cls.db.sheet_connections.create_index(
            [("user_id", ASCENDING), ("organization_id", ASCENDING)],
            name="idx_sheet_connections_user_org",
            background=True,
        )
        logger.info("Created index: idx_sheet_connections_user_org")

        await cls.db.sheet_connections.create_index(
            [("sync_enabled", ASCENDING), ("organization_id", ASCENDING)],
            name="idx_sheet_connections_sync_org",
            background=True,
        )
        logger.info("Created index: idx_sheet_connections_sync_org")

        # Index for messages collection
        # Supports: get_by_conversation() with chronological ordering
        # Requirements: 2.2 (retrieve by conversation_id in chronological order)
        await cls.db.messages.create_index(
            [
                ("conversation_id", ASCENDING),
                ("deleted_at", ASCENDING),
                ("created_at", ASCENDING),
            ],
            name="idx_messages_conversation_deleted_created",
            background=True,
        )
        logger.info("Created index: idx_messages_conversation_deleted_created")
