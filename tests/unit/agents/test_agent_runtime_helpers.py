from __future__ import annotations

from types import SimpleNamespace

from app.agents import runtime


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "ZAI_API_KEY": None,
        "MINIMAX_API_KEY": None,
        "OPENAI_API_KEY": None,
        "AZURE_OPENAI_API_KEY": None,
        "AZURE_OPENAI_ENDPOINT": None,
        "AZURE_OPENAI_API_VERSION": None,
        "AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_runtime_catalog_honors_configured_default_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: _settings(ZAI_API_KEY="zai-key", OPENAI_API_KEY="openai-key"),
    )

    catalog = runtime.build_runtime_catalog(
        zai_models=(runtime.AgentModelCatalogEntry(model="glm-5.1"),),
        openai_models=(runtime.AgentModelCatalogEntry(model="gpt-5.4"),),
        default_provider=runtime.AGENT_PROVIDER_OPENAI,
    )

    assert [(entry.provider, entry.is_default) for entry in catalog] == [
        ("zai", False),
        ("openai", True),
    ]


def test_build_runtime_catalog_falls_back_when_requested_default_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(runtime, "get_settings", lambda: _settings(ZAI_API_KEY="zai-key"))

    catalog = runtime.build_runtime_catalog(
        zai_models=(runtime.AgentModelCatalogEntry(model="glm-5.1"),),
        openai_models=(runtime.AgentModelCatalogEntry(model="gpt-5.4"),),
        default_provider=runtime.AGENT_PROVIDER_OPENAI,
    )

    assert [(entry.provider, entry.is_default) for entry in catalog] == [
        ("zai", True),
    ]
