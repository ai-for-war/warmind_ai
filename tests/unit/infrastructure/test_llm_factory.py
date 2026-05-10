from __future__ import annotations

from types import SimpleNamespace

from app.infrastructure.llm import factory


def test_get_chat_openai_enables_stream_usage_when_streaming(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(factory, "ChatOpenAI", _fake_chat_openai)
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: SimpleNamespace(
            OPENAI_API_KEY="test-key",
            OPENAI_API_BASE="https://example.test",
        ),
    )

    factory.get_chat_openai(model="gpt-5.2", streaming=True)

    assert captured["stream_usage"] is True
    assert captured["streaming"] is True


def test_get_chat_openai_uses_responses_api_reasoning(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(factory, "ChatOpenAI", _fake_chat_openai)
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: SimpleNamespace(
            OPENAI_API_KEY="test-key",
            OPENAI_API_BASE="https://example.test",
        ),
    )

    factory.get_chat_openai(model="gpt-5.5", reasoning_effort="medium")

    assert captured["use_responses_api"] is True
    assert captured["reasoning"] == {"effort": "medium"}
    assert "service_tier" not in captured
    # assert "reasoning_effort" not in captured


def test_get_chat_openai_maps_gpt_5_5_fast_to_priority_gpt_5_5(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(factory, "ChatOpenAI", _fake_chat_openai)
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: SimpleNamespace(
            OPENAI_API_KEY="test-key",
            OPENAI_API_BASE="https://example.test",
        ),
    )

    factory.get_chat_openai(model="gpt-5.5-fast", reasoning_effort="medium")

    assert captured["model"] == "gpt-5.5"
    assert captured["service_tier"] == "priority"


def test_get_chat_azure_openai_enables_stream_usage_when_streaming(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_azure_chat_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(factory, "AzureChatOpenAI", _fake_azure_chat_openai)
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: SimpleNamespace(
            AZURE_OPENAI_API_KEY="test-key",
            AZURE_OPENAI_ENDPOINT="https://azure.example.test",
            AZURE_OPENAI_API_VERSION="2025-03-01-preview",
            AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT="gpt-4.1",
        ),
    )

    factory.get_chat_azure_openai_legacy(model="gpt-4.1", streaming=True)

    assert captured["stream_usage"] is True
    assert captured["streaming"] is True
