"""Shared LangGraph MongoDB checkpointer infrastructure."""

import asyncio

from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient

CHECKPOINT_COLLECTION_NAME = "langgraph_checkpoints"
WRITES_COLLECTION_NAME = "langgraph_checkpoint_writes"


class LangGraphCheckpointer:
    """Lifecycle-managed shared LangGraph checkpointer."""

    _checkpointer: MongoDBSaver | None = None

    @classmethod
    async def connect(cls, uri: str, db_name: str) -> None:
        """Initialize the shared MongoDB-backed LangGraph checkpointer."""
        if cls._checkpointer is not None:
            return

        cls._checkpointer = await asyncio.to_thread(
            cls._create_checkpointer,
            uri,
            db_name,
        )

    @staticmethod
    def _create_checkpointer(uri: str, db_name: str) -> MongoDBSaver:
        """Build a MongoDBSaver using the application's MongoDB settings."""
        client = MongoClient(uri)
        return MongoDBSaver(
            client=client,
            db_name=db_name,
            checkpoint_collection_name=CHECKPOINT_COLLECTION_NAME,
            writes_collection_name=WRITES_COLLECTION_NAME,
        )

    @classmethod
    async def disconnect(cls) -> None:
        """Close the shared LangGraph checkpointer."""
        if cls._checkpointer is None:
            return

        checkpointer = cls._checkpointer
        cls._checkpointer = None
        await asyncio.to_thread(checkpointer.close)

    @classmethod
    def get_checkpointer(cls) -> MongoDBSaver:
        """Return the initialized shared LangGraph checkpointer."""
        if cls._checkpointer is None:
            raise RuntimeError(
                "LangGraph checkpointer not initialized. Call connect() first."
            )
        return cls._checkpointer


def get_langgraph_checkpointer() -> MongoDBSaver:
    """Expose the shared LangGraph checkpointer."""
    return LangGraphCheckpointer.get_checkpointer()
