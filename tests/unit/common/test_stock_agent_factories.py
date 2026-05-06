from __future__ import annotations

from types import SimpleNamespace

from app.common import repo as repo_module
from app.repo.stock_agent_conversation_repo import StockAgentConversationRepository
from app.repo.stock_agent_message_repo import StockAgentMessageRepository
from app.repo.stock_agent_skill_access_repo import StockAgentSkillAccessRepository
from app.repo.stock_agent_skill_repo import StockAgentSkillRepository


def test_stock_agent_repository_factories_target_stock_agent_collections(
    monkeypatch,
) -> None:
    fake_db = SimpleNamespace(
        stock_agent_conversations=object(),
        stock_agent_messages=object(),
        stock_agent_skills=object(),
        stock_agent_skill_access=object(),
    )
    monkeypatch.setattr(repo_module.MongoDB, "get_db", lambda: fake_db)

    repo_module.get_stock_agent_conversation_repo.cache_clear()
    repo_module.get_stock_agent_message_repo.cache_clear()
    repo_module.get_stock_agent_skill_repo.cache_clear()
    repo_module.get_stock_agent_skill_access_repo.cache_clear()

    conversation_repo = repo_module.get_stock_agent_conversation_repo()
    message_repo = repo_module.get_stock_agent_message_repo()
    skill_repo = repo_module.get_stock_agent_skill_repo()
    access_repo = repo_module.get_stock_agent_skill_access_repo()

    assert isinstance(conversation_repo, StockAgentConversationRepository)
    assert isinstance(message_repo, StockAgentMessageRepository)
    assert isinstance(skill_repo, StockAgentSkillRepository)
    assert isinstance(access_repo, StockAgentSkillAccessRepository)
    assert conversation_repo.collection is fake_db.stock_agent_conversations
    assert message_repo.collection is fake_db.stock_agent_messages
    assert skill_repo.collection is fake_db.stock_agent_skills
    assert access_repo.collection is fake_db.stock_agent_skill_access
