"""MongoDB async client using motor."""

import logging
from datetime import timezone

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
        cls.client = AsyncIOMotorClient(uri, tz_aware=True, tzinfo=timezone.utc)
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
        - lead_agent_skills: (created_by, organization_id, skill_id) unique
        - lead_agent_skills: (created_by, organization_id, updated_at DESC)
        - lead_agent_skill_access: (user_id, organization_id) unique
        - conversations: (user_id, organization_id, deleted_at, updated_at DESC)
          for user listing in organization scope
        - conversations: (user_id, organization_id, deleted_at, thread_id, updated_at DESC)
          for runtime-aware conversation listing
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

        # Indexes for persisted lead-agent skills collection
        existing_skill_indexes = await cls.db.lead_agent_skills.index_information()
        if "idx_lead_agent_skills_skill_id_unique" in existing_skill_indexes:
            await cls.db.lead_agent_skills.drop_index(
                "idx_lead_agent_skills_skill_id_unique"
            )
            logger.info("Dropped legacy index: idx_lead_agent_skills_skill_id_unique")

        await cls.db.lead_agent_skills.create_index(
            [
                ("created_by", ASCENDING),
                ("organization_id", ASCENDING),
                ("skill_id", ASCENDING),
            ],
            name="idx_lead_agent_skills_creator_org_skill_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_lead_agent_skills_creator_org_skill_unique")

        await cls.db.lead_agent_skills.create_index(
            [
                ("created_by", ASCENDING),
                ("organization_id", ASCENDING),
                ("updated_at", DESCENDING),
            ],
            name="idx_lead_agent_skills_creator_org_updated",
            background=True,
        )
        logger.info("Created index: idx_lead_agent_skills_creator_org_updated")

        # Index for lead-agent skill access collection
        await cls.db.lead_agent_skill_access.create_index(
            [("user_id", ASCENDING), ("organization_id", ASCENDING)],
            name="idx_lead_agent_skill_access_user_org_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_lead_agent_skill_access_user_org_unique")

        # Indexes for persisted stock-agent skills collection
        await cls.db.stock_agent_skills.create_index(
            [
                ("created_by", ASCENDING),
                ("organization_id", ASCENDING),
                ("skill_id", ASCENDING),
            ],
            name="idx_stock_agent_skills_creator_org_skill_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_stock_agent_skills_creator_org_skill_unique")

        await cls.db.stock_agent_skills.create_index(
            [
                ("created_by", ASCENDING),
                ("organization_id", ASCENDING),
                ("updated_at", DESCENDING),
            ],
            name="idx_stock_agent_skills_creator_org_updated",
            background=True,
        )
        logger.info("Created index: idx_stock_agent_skills_creator_org_updated")

        # Index for stock-agent skill access collection
        await cls.db.stock_agent_skill_access.create_index(
            [("user_id", ASCENDING), ("organization_id", ASCENDING)],
            name="idx_stock_agent_skill_access_user_org_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_stock_agent_skill_access_user_org_unique")

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

        await cls.db.conversations.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("deleted_at", ASCENDING),
                ("thread_id", ASCENDING),
                ("updated_at", DESCENDING),
            ],
            name="idx_conversations_user_org_deleted_thread_updated",
            background=True,
        )
        logger.info("Created index: idx_conversations_user_org_deleted_thread_updated")

        # Indexes for stock-agent conversations collection
        await cls.db.stock_agent_conversations.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("deleted_at", ASCENDING),
                ("updated_at", DESCENDING),
            ],
            name="idx_stock_agent_conversations_user_org_deleted_updated",
            background=True,
        )
        logger.info(
            "Created index: idx_stock_agent_conversations_user_org_deleted_updated"
        )

        await cls.db.stock_agent_conversations.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("deleted_at", ASCENDING),
                ("thread_id", ASCENDING),
                ("updated_at", DESCENDING),
            ],
            name="idx_stock_agent_conversations_user_org_deleted_thread_updated",
            background=True,
        )
        logger.info(
            "Created index: "
            "idx_stock_agent_conversations_user_org_deleted_thread_updated"
        )

        # Index for interview conversations collection
        # Supports: stable lookup by conversation_id during interview session flows
        await cls.db.interview_conversations.create_index(
            [("conversation_id", ASCENDING)],
            name="idx_interview_conversations_conversation_id_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_interview_conversations_conversation_id_unique")

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

        # Indexes for stock_symbols collection
        await cls.db.stock_symbols.create_index(
            [("symbol", ASCENDING)],
            name="idx_stock_symbols_symbol_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_stock_symbols_symbol_unique")

        await cls.db.stock_symbols.create_index(
            [("exchange", ASCENDING)],
            name="idx_stock_symbols_exchange",
            background=True,
        )
        logger.info("Created index: idx_stock_symbols_exchange")

        await cls.db.stock_symbols.create_index(
            [("groups", ASCENDING)],
            name="idx_stock_symbols_groups",
            background=True,
        )
        logger.info("Created index: idx_stock_symbols_groups")

        await cls.db.stock_symbols.create_index(
            [("normalized_symbol", ASCENDING)],
            name="idx_stock_symbols_normalized_symbol",
            background=True,
        )
        logger.info("Created index: idx_stock_symbols_normalized_symbol")

        await cls.db.stock_symbols.create_index(
            [("normalized_organ_name", ASCENDING)],
            name="idx_stock_symbols_normalized_organ_name",
            background=True,
        )
        logger.info("Created index: idx_stock_symbols_normalized_organ_name")

        await cls.db.stock_symbols.create_index(
            [("snapshot_at", ASCENDING)],
            name="idx_stock_symbols_snapshot_at",
            background=True,
        )
        logger.info("Created index: idx_stock_symbols_snapshot_at")

        # Indexes for stock_research_reports collection
        await cls.db.stock_research_reports.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            name="idx_stock_research_reports_user_org_created_desc",
            background=True,
        )
        logger.info("Created index: idx_stock_research_reports_user_org_created_desc")

        await cls.db.stock_research_reports.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("symbol", ASCENDING),
                ("created_at", DESCENDING),
            ],
            name="idx_stock_research_reports_user_org_symbol_created_desc",
            background=True,
        )
        logger.info(
            "Created index: idx_stock_research_reports_user_org_symbol_created_desc"
        )

        await cls.db.stock_research_reports.create_index(
            [
                ("status", ASCENDING),
                ("updated_at", DESCENDING),
            ],
            name="idx_stock_research_reports_status_updated_desc",
            background=True,
        )
        logger.info("Created index: idx_stock_research_reports_status_updated_desc")

        # Indexes for stock_research_schedules collection
        await cls.db.stock_research_schedules.create_index(
            [
                ("status", ASCENDING),
                ("next_run_at", ASCENDING),
            ],
            name="idx_stock_research_schedules_status_next_run",
            background=True,
        )
        logger.info("Created index: idx_stock_research_schedules_status_next_run")

        await cls.db.stock_research_schedules.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            name="idx_stock_research_schedules_user_org_created_desc",
            background=True,
        )
        logger.info(
            "Created index: idx_stock_research_schedules_user_org_created_desc"
        )

        # Indexes for stock_research_schedule_runs collection
        await cls.db.stock_research_schedule_runs.create_index(
            [
                ("schedule_id", ASCENDING),
                ("occurrence_at", ASCENDING),
            ],
            name="idx_stock_research_schedule_runs_schedule_occurrence_unique",
            unique=True,
            background=True,
        )
        logger.info(
            "Created index: "
            "idx_stock_research_schedule_runs_schedule_occurrence_unique"
        )

        # Indexes for stock_watchlists collection
        await cls.db.stock_watchlists.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("normalized_name", ASCENDING),
            ],
            name="idx_stock_watchlists_user_org_name_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_stock_watchlists_user_org_name_unique")

        # Additive index for scoped watchlist listing ordered by most recent update.
        await cls.db.stock_watchlists.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("updated_at", DESCENDING),
            ],
            name="idx_stock_watchlists_user_org_updated",
            background=True,
        )
        logger.info("Created index: idx_stock_watchlists_user_org_updated")

        # Indexes for stock_watchlist_items collection
        await cls.db.stock_watchlist_items.create_index(
            [("watchlist_id", ASCENDING), ("normalized_symbol", ASCENDING)],
            name="idx_stock_watchlist_items_watchlist_symbol_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_stock_watchlist_items_watchlist_symbol_unique")

        # Additive index for newest-first item reads within one watchlist.
        await cls.db.stock_watchlist_items.create_index(
            [("watchlist_id", ASCENDING), ("saved_at", DESCENDING)],
            name="idx_stock_watchlist_items_watchlist_saved_desc",
            background=True,
        )
        logger.info("Created index: idx_stock_watchlist_items_watchlist_saved_desc")

        # Indexes for notifications collection
        await cls.db.notifications.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            name="idx_notifications_user_org_created_desc",
            background=True,
        )
        logger.info("Created index: idx_notifications_user_org_created_desc")

        await cls.db.notifications.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("is_read", ASCENDING),
                ("created_at", DESCENDING),
            ],
            name="idx_notifications_user_org_read_created_desc",
            background=True,
        )
        logger.info("Created index: idx_notifications_user_org_read_created_desc")

        await cls.db.notifications.create_index(
            [
                ("user_id", ASCENDING),
                ("organization_id", ASCENDING),
                ("dedupe_key", ASCENDING),
            ],
            name="idx_notifications_user_org_dedupe_unique",
            unique=True,
            background=True,
            partialFilterExpression={"dedupe_key": {"$type": "string"}},
        )
        logger.info("Created index: idx_notifications_user_org_dedupe_unique")

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

        # Index for stock-agent messages collection
        await cls.db.stock_agent_messages.create_index(
            [
                ("conversation_id", ASCENDING),
                ("deleted_at", ASCENDING),
                ("created_at", ASCENDING),
            ],
            name="idx_stock_agent_messages_conversation_deleted_created",
            background=True,
        )
        logger.info(
            "Created index: idx_stock_agent_messages_conversation_deleted_created"
        )

        # Indexes for interview_utterances collection
        # Supports: recovery queries by created_at and timeline ordering by turn_closed_at
        await cls.db.interview_utterances.create_index(
            [("conversation_id", ASCENDING), ("created_at", ASCENDING)],
            name="idx_interview_utterances_conversation_created",
            background=True,
        )
        logger.info("Created index: idx_interview_utterances_conversation_created")

        await cls.db.interview_utterances.create_index(
            [("conversation_id", ASCENDING), ("turn_closed_at", ASCENDING)],
            name="idx_interview_utterances_conversation_turn_closed",
            background=True,
        )
        logger.info("Created index: idx_interview_utterances_conversation_turn_closed")

        # Indexes for meetings collection
        await cls.db.meetings.create_index(
            [("organization_id", ASCENDING), ("started_at", DESCENDING)],
            name="idx_meetings_organization_started_desc",
            background=True,
        )
        logger.info("Created index: idx_meetings_organization_started_desc")

        await cls.db.meetings.create_index(
            [
                ("created_by", ASCENDING),
                ("organization_id", ASCENDING),
                ("started_at", DESCENDING),
            ],
            name="idx_meetings_creator_org_started_desc",
            background=True,
        )
        logger.info("Created index: idx_meetings_creator_org_started_desc")

        await cls.db.meetings.create_index(
            [("status", ASCENDING), ("started_at", DESCENDING)],
            name="idx_meetings_status_started_desc",
            background=True,
        )
        logger.info("Created index: idx_meetings_status_started_desc")

        # Unique sequence index for idempotent meeting utterance persistence
        await cls.db.meeting_utterances.create_index(
            [("meeting_id", ASCENDING), ("sequence", ASCENDING)],
            name="idx_meeting_utterances_meeting_sequence_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_meeting_utterances_meeting_sequence_unique")

        # Unique range index for idempotent meeting note chunk persistence
        await cls.db.meeting_note_chunks.create_index(
            [
                ("meeting_id", ASCENDING),
                ("from_sequence", ASCENDING),
                ("to_sequence", ASCENDING),
            ],
            name="idx_meeting_note_chunks_meeting_range_unique",
            unique=True,
            background=True,
        )
        logger.info("Created index: idx_meeting_note_chunks_meeting_range_unique")

        # Indexes for image_generation_jobs collection
        await cls.db.image_generation_jobs.create_index(
            [
                ("organization_id", ASCENDING),
                ("requested_at", DESCENDING),
                ("deleted_at", ASCENDING),
            ],
            name="idx_image_gen_jobs_org_requested_deleted",
            background=True,
        )
        logger.info("Created index: idx_image_gen_jobs_org_requested_deleted")

        await cls.db.image_generation_jobs.create_index(
            [
                ("created_by", ASCENDING),
                ("organization_id", ASCENDING),
                ("requested_at", DESCENDING),
                ("deleted_at", ASCENDING),
            ],
            name="idx_image_gen_jobs_creator_org_requested_deleted",
            background=True,
        )
        logger.info("Created index: idx_image_gen_jobs_creator_org_requested_deleted")

        await cls.db.image_generation_jobs.create_index(
            [
                ("status", ASCENDING),
                ("requested_at", DESCENDING),
                ("deleted_at", ASCENDING),
            ],
            name="idx_image_gen_jobs_status_requested_deleted",
            background=True,
        )
        logger.info("Created index: idx_image_gen_jobs_status_requested_deleted")

        # Additive index for generated image linkage in images collection.
        await cls.db.images.create_index(
            [("generation_job_id", ASCENDING), ("deleted_at", ASCENDING)],
            name="idx_images_generation_job_deleted",
            background=True,
        )
        logger.info("Created index: idx_images_generation_job_deleted")
