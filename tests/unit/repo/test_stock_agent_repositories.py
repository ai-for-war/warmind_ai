from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
import pytest
from pymongo import ReturnDocument

from app.domain.models.message import MessageRole
from app.repo.stock_agent_conversation_repo import StockAgentConversationRepository
from app.repo.stock_agent_message_repo import StockAgentMessageRepository
from app.repo.stock_agent_skill_access_repo import StockAgentSkillAccessRepository
from app.repo.stock_agent_skill_repo import StockAgentSkillRepository


def _matches_query(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for field_name, expected in query.items():
        actual = document.get(field_name)
        if isinstance(expected, dict):
            if "$in" in expected:
                if actual not in expected["$in"]:
                    return False
                continue
            if "$nin" in expected:
                if actual in expected["$nin"]:
                    return False
                continue
            if "$exists" in expected:
                exists = field_name in document
                if exists is not expected["$exists"]:
                    return False
            if "$ne" in expected:
                if actual == expected["$ne"]:
                    return False
            continue
        if actual != expected:
            return False
    return True


class _InsertResult:
    def __init__(self, inserted_id: ObjectId) -> None:
        self.inserted_id = inserted_id


class _DeleteResult:
    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class _UpdateResult:
    def __init__(self, modified_count: int) -> None:
        self.modified_count = modified_count


class _FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = [deepcopy(document) for document in documents]
        self._iterator: iter[dict[str, Any]] | None = None

    def sort(self, fields, direction: int | None = None) -> "_FakeCursor":
        normalized_fields = [(fields, direction)] if isinstance(fields, str) else fields
        for field_name, field_direction in reversed(list(normalized_fields)):
            reverse = field_direction in {-1}
            self._documents.sort(
                key=lambda document: document.get(field_name),
                reverse=reverse,
            )
        return self

    def skip(self, count: int) -> "_FakeCursor":
        self._documents = self._documents[count:]
        return self

    def limit(self, count: int) -> "_FakeCursor":
        self._documents = self._documents[:count]
        return self

    def __aiter__(self) -> "_FakeCursor":
        self._iterator = iter(self._documents)
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._iterator is None:
            self._iterator = iter(self._documents)
        try:
            return deepcopy(next(self._iterator))
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    async def insert_one(self, payload: dict[str, Any]) -> _InsertResult:
        document = deepcopy(payload)
        inserted_id = ObjectId()
        document["_id"] = inserted_id
        self.documents.append(document)
        return _InsertResult(inserted_id)

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for document in self.documents:
            if _matches_query(document, query):
                return deepcopy(document)
        return None

    def find(self, query: dict[str, Any]) -> _FakeCursor:
        return _FakeCursor(
            [document for document in self.documents if _matches_query(document, query)]
        )

    async def find_one_and_update(
        self,
        query: dict[str, Any],
        update: dict[str, dict[str, Any]],
        *,
        upsert: bool = False,
        return_document: ReturnDocument | bool | None = None,
    ) -> dict[str, Any] | None:
        for index, document in enumerate(self.documents):
            if not _matches_query(document, query):
                continue
            updated = deepcopy(document)
            updated.update(update.get("$set", {}))
            self.documents[index] = updated
            return deepcopy(updated)

        if not upsert:
            return None

        inserted = {
            "_id": ObjectId(),
            **deepcopy(query),
            **deepcopy(update.get("$setOnInsert", {})),
            **deepcopy(update.get("$set", {})),
        }
        self.documents.append(inserted)
        return deepcopy(inserted)

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, dict[str, Any]],
    ) -> _UpdateResult:
        for index, document in enumerate(self.documents):
            if not _matches_query(document, query):
                continue
            updated = deepcopy(document)
            updated.update(update.get("$set", {}))
            self.documents[index] = updated
            return _UpdateResult(1)
        return _UpdateResult(0)

    async def delete_one(self, query: dict[str, Any]) -> _DeleteResult:
        for index, document in enumerate(self.documents):
            if _matches_query(document, query):
                del self.documents[index]
                return _DeleteResult(1)
        return _DeleteResult(0)

    async def delete_many(self, query: dict[str, Any]) -> _DeleteResult:
        retained = []
        deleted = 0
        for document in self.documents:
            if _matches_query(document, query):
                deleted += 1
            else:
                retained.append(document)
        self.documents = retained
        return _DeleteResult(deleted)

    async def count_documents(
        self,
        query: dict[str, Any],
        limit: int | None = None,
    ) -> int:
        count = 0
        for document in self.documents:
            if _matches_query(document, query):
                count += 1
                if limit is not None and count >= limit:
                    return count
        return count


class _ForbiddenCollection:
    def __getattr__(self, name: str):
        raise AssertionError(f"Unexpected access to forbidden collection method {name}")


class _FakeDB:
    def __init__(self) -> None:
        self.stock_agent_conversations = _FakeCollection()
        self.stock_agent_messages = _FakeCollection()
        self.stock_agent_skills = _FakeCollection()
        self.stock_agent_skill_access = _FakeCollection()
        self.conversations = _ForbiddenCollection()
        self.messages = _ForbiddenCollection()
        self.lead_agent_skills = _ForbiddenCollection()
        self.lead_agent_skill_access = _ForbiddenCollection()


@pytest.mark.asyncio
async def test_stock_agent_conversation_repository_writes_stock_collection_only() -> None:
    db = _FakeDB()
    repository = StockAgentConversationRepository(db)

    conversation = await repository.create(
        user_id="user-1",
        organization_id="org-1",
        thread_id="thread-1",
    )

    assert conversation.user_id == "user-1"
    assert conversation.thread_id == "thread-1"
    assert len(db.stock_agent_conversations.documents) == 1


@pytest.mark.asyncio
async def test_stock_agent_message_repository_writes_stock_collection_only() -> None:
    db = _FakeDB()
    repository = StockAgentMessageRepository(db)

    message = await repository.create(
        conversation_id="conversation-1",
        role=MessageRole.USER,
        content="hello",
        thread_id="thread-1",
    )

    assert message.conversation_id == "conversation-1"
    assert message.thread_id == "thread-1"
    assert len(db.stock_agent_messages.documents) == 1


@pytest.mark.asyncio
async def test_stock_agent_skill_repository_writes_stock_collection_only() -> None:
    db = _FakeDB()
    repository = StockAgentSkillRepository(db)

    skill = await repository.create(
        skill_id="research",
        name="Research",
        description="Research sources",
        activation_prompt="Use sources",
        allowed_tool_names=["search", " search "],
        version="1.0.0",
        created_by="user-1",
        organization_id="org-1",
    )

    assert skill.skill_id == "research"
    assert skill.allowed_tool_names == ["search"]
    assert len(db.stock_agent_skills.documents) == 1


@pytest.mark.asyncio
async def test_stock_agent_skill_access_repository_writes_stock_collection_only() -> None:
    db = _FakeDB()
    repository = StockAgentSkillAccessRepository(db)

    access = await repository.upsert_enabled_skills(
        user_id="user-1",
        organization_id="org-1",
        enabled_skill_ids=["research", "research", " "],
    )

    assert access.enabled_skill_ids == ["research"]
    assert len(db.stock_agent_skill_access.documents) == 1


def test_stock_agent_repositories_bind_to_stock_agent_collections() -> None:
    db = _FakeDB()

    assert StockAgentConversationRepository(db).collection is db.stock_agent_conversations
    assert StockAgentMessageRepository(db).collection is db.stock_agent_messages
    assert StockAgentSkillRepository(db).collection is db.stock_agent_skills
    assert StockAgentSkillAccessRepository(db).collection is db.stock_agent_skill_access
