from __future__ import annotations


def test_runtime_catalog_exposes_gpt_5_5() -> None:
    import app.agents.implementations.stock_research_agent.runtime as runtime

    runtime.get_stock_research_runtime_catalog.cache_clear()
    try:
        catalog = runtime.get_stock_research_runtime_catalog()
        openai_provider = next(
            provider for provider in catalog if provider.provider == "openai"
        )
        model = next(
            model for model in openai_provider.models if model.model == "gpt-5.5"
        )
        fast_model = next(
            model
            for model in openai_provider.models
            if model.model == "gpt-5.5-fast"
        )

        assert model.default_reasoning == "medium"
        assert "medium" in model.reasoning_options
        assert model.is_default is True
        assert fast_model.default_reasoning == "medium"
        assert "medium" in fast_model.reasoning_options
        assert fast_model.is_default is False
    finally:
        runtime.get_stock_research_runtime_catalog.cache_clear()
