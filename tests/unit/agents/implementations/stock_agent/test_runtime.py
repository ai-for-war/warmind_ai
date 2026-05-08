from __future__ import annotations

import pytest

from app.common.exceptions import AppException


@pytest.fixture
def runtime_module():
    import app.agents.implementations.stock_agent.runtime as runtime

    runtime.get_stock_agent_runtime_catalog.cache_clear()
    yield runtime
    runtime.get_stock_agent_runtime_catalog.cache_clear()


def test_resolve_runtime_requires_reasoning_for_models_that_support_it(
    runtime_module,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "get_stock_agent_runtime_catalog",
        lambda: (
            runtime_module.StockAgentProviderCatalogEntry(
                provider="openai",
                display_name="OpenAI",
                is_default=True,
                models=(
                    runtime_module.StockAgentModelCatalogEntry(
                        model="gpt-5.2",
                        reasoning_options=("low", "medium", "high"),
                        default_reasoning="high",
                        is_default=True,
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(AppException) as exc_info:
        runtime_module.resolve_stock_agent_runtime_config(
            provider="openai",
            model="gpt-5.2",
            reasoning=None,
        )

    assert "Reasoning is required" in exc_info.value.message


def test_resolve_runtime_requires_provider_and_model(
    runtime_module,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "get_stock_agent_runtime_catalog",
        lambda: (
            runtime_module.StockAgentProviderCatalogEntry(
                provider="openai",
                display_name="OpenAI",
                is_default=True,
                models=(
                    runtime_module.StockAgentModelCatalogEntry(
                        model="gpt-4.1",
                        is_default=True,
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(AppException) as missing_provider_exc:
        runtime_module.resolve_stock_agent_runtime_config(
            provider="",
            model="gpt-4.1",
            reasoning=None,
        )

    with pytest.raises(AppException) as missing_model_exc:
        runtime_module.resolve_stock_agent_runtime_config(
            provider="openai",
            model="",
            reasoning=None,
        )

    assert missing_provider_exc.value.message == "Stock-agent provider is required"
    assert missing_model_exc.value.message == "Stock-agent model is required"


def test_resolve_runtime_allows_null_reasoning_for_models_without_reasoning_support(
    runtime_module,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "get_stock_agent_runtime_catalog",
        lambda: (
            runtime_module.StockAgentProviderCatalogEntry(
                provider="openai",
                display_name="OpenAI",
                is_default=True,
                models=(
                    runtime_module.StockAgentModelCatalogEntry(
                        model="gpt-4.1",
                        is_default=True,
                    ),
                ),
            ),
        ),
    )

    runtime_config = runtime_module.resolve_stock_agent_runtime_config(
        provider="openai",
        model="gpt-4.1",
        reasoning=None,
    )

    assert runtime_config == runtime_module.StockAgentRuntimeConfig(
        provider="openai",
        model="gpt-4.1",
        reasoning=None,
    )


def test_runtime_catalog_exposes_gpt_5_5(runtime_module) -> None:
    catalog = runtime_module.get_stock_agent_runtime_catalog()
    openai_provider = next(provider for provider in catalog if provider.provider == "openai")
    model = next(model for model in openai_provider.models if model.model == "gpt-5.5")

    assert model.default_reasoning == "medium"
    assert "medium" in model.reasoning_options
    assert model.is_default is True
