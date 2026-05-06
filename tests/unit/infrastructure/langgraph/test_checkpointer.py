from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

import pytest

mongodb_checkpoint_module = ModuleType("langgraph.checkpoint.mongodb")


class _MongoDBSaver:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)

    def close(self) -> None:
        return None


mongodb_checkpoint_module.MongoDBSaver = _MongoDBSaver
sys.modules.setdefault("langgraph.checkpoint.mongodb", mongodb_checkpoint_module)

from app.infrastructure.langgraph import checkpointer as checkpointer_module


def test_stock_agent_checkpointer_uses_stock_agent_collections(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_mongo_client(uri: str) -> SimpleNamespace:
        captured["uri"] = uri
        return SimpleNamespace(uri=uri)

    def _fake_mongodb_saver(**kwargs) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(**kwargs, close=lambda: None)

    monkeypatch.setattr(checkpointer_module, "MongoClient", _fake_mongo_client)
    monkeypatch.setattr(checkpointer_module, "MongoDBSaver", _fake_mongodb_saver)

    saver = checkpointer_module.StockAgentLangGraphCheckpointer._create_checkpointer(
        "mongodb://test",
        "ai_service_test",
    )

    assert saver is not None
    assert captured["uri"] == "mongodb://test"
    assert captured["db_name"] == "ai_service_test"
    assert (
        captured["checkpoint_collection_name"]
        == checkpointer_module.STOCK_AGENT_CHECKPOINT_COLLECTION_NAME
    )
    assert (
        captured["writes_collection_name"]
        == checkpointer_module.STOCK_AGENT_WRITES_COLLECTION_NAME
    )
    assert (
        captured["checkpoint_collection_name"]
        != checkpointer_module.CHECKPOINT_COLLECTION_NAME
    )
    assert captured["writes_collection_name"] != checkpointer_module.WRITES_COLLECTION_NAME


def test_shared_checkpointer_keeps_shared_collections(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        checkpointer_module,
        "MongoClient",
        lambda uri: SimpleNamespace(uri=uri),
    )
    monkeypatch.setattr(
        checkpointer_module,
        "MongoDBSaver",
        lambda **kwargs: captured.update(kwargs) or SimpleNamespace(**kwargs),
    )

    checkpointer_module.LangGraphCheckpointer._create_checkpointer(
        "mongodb://test",
        "ai_service_test",
    )

    assert (
        captured["checkpoint_collection_name"]
        == checkpointer_module.CHECKPOINT_COLLECTION_NAME
    )
    assert captured["writes_collection_name"] == checkpointer_module.WRITES_COLLECTION_NAME


@pytest.mark.asyncio
async def test_stock_agent_checkpointer_lifecycle_is_independent(monkeypatch) -> None:
    close_calls: list[str] = []
    stock_saver = SimpleNamespace(close=lambda: close_calls.append("stock"))
    shared_saver = SimpleNamespace(close=lambda: close_calls.append("shared"))

    monkeypatch.setattr(
        checkpointer_module.StockAgentLangGraphCheckpointer,
        "_create_checkpointer",
        lambda uri, db_name: stock_saver,
    )
    monkeypatch.setattr(
        checkpointer_module.LangGraphCheckpointer,
        "_create_checkpointer",
        lambda uri, db_name: shared_saver,
    )
    checkpointer_module.StockAgentLangGraphCheckpointer._checkpointer = None
    checkpointer_module.LangGraphCheckpointer._checkpointer = None

    try:
        await checkpointer_module.LangGraphCheckpointer.connect("mongodb://test", "db")
        await checkpointer_module.StockAgentLangGraphCheckpointer.connect(
            "mongodb://test",
            "db",
        )

        assert checkpointer_module.get_langgraph_checkpointer() is shared_saver
        assert checkpointer_module.get_stock_agent_langgraph_checkpointer() is stock_saver
    finally:
        await checkpointer_module.StockAgentLangGraphCheckpointer.disconnect()
        await checkpointer_module.LangGraphCheckpointer.disconnect()

    assert close_calls == ["stock", "shared"]
