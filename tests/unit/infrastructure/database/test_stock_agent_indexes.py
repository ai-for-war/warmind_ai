from __future__ import annotations

from typing import Any

import pytest

from app.infrastructure.database.mongodb import MongoDB


class _FakeIndexCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.created_indexes: list[dict[str, Any]] = []

    async def index_information(self) -> dict[str, Any]:
        return {}

    async def drop_index(self, name: str) -> None:
        return None

    async def create_index(self, fields, **kwargs) -> None:
        self.created_indexes.append({"fields": fields, **kwargs})


class _FakeIndexDB:
    def __init__(self) -> None:
        self.collections: dict[str, _FakeIndexCollection] = {}

    def __getattr__(self, name: str) -> _FakeIndexCollection:
        collection = self.collections.get(name)
        if collection is None:
            collection = _FakeIndexCollection(name)
            self.collections[name] = collection
        return collection


@pytest.mark.asyncio
async def test_create_indexes_adds_stock_agent_collection_indexes() -> None:
    fake_db = _FakeIndexDB()
    original_db = getattr(MongoDB, "db", None)
    MongoDB.db = fake_db

    try:
        await MongoDB.create_indexes()
    finally:
        MongoDB.db = original_db

    assert {
        index["name"]
        for index in fake_db.collections["stock_agent_skills"].created_indexes
    } == {
        "idx_stock_agent_skills_creator_org_skill_unique",
        "idx_stock_agent_skills_creator_org_updated",
    }
    assert {
        index["name"]
        for index in fake_db.collections["stock_agent_skill_access"].created_indexes
    } == {"idx_stock_agent_skill_access_user_org_unique"}
    assert {
        index["name"]
        for index in fake_db.collections["stock_agent_conversations"].created_indexes
    } == {
        "idx_stock_agent_conversations_user_org_deleted_updated",
        "idx_stock_agent_conversations_user_org_deleted_thread_updated",
    }
    assert {
        index["name"]
        for index in fake_db.collections["stock_agent_messages"].created_indexes
    } == {"idx_stock_agent_messages_conversation_deleted_created"}

    assert "stock_agent_skills" in fake_db.collections
    assert "lead_agent_skills" in fake_db.collections
    assert fake_db.collections["stock_agent_skills"] is not fake_db.collections[
        "lead_agent_skills"
    ]
