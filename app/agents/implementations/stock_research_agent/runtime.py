"""Runtime helpers for stock-research agent execution."""

from __future__ import annotations

from functools import lru_cache

from app.agents.runtime import (
    AGENT_OPENAI_REASONING_OPTIONS as STOCK_RESEARCH_OPENAI_REASONING_OPTIONS,
    AGENT_PROVIDER_AZURA as STOCK_RESEARCH_PROVIDER_AZURA,
    AGENT_PROVIDER_MINIMAX as STOCK_RESEARCH_PROVIDER_MINIMAX,
    AGENT_PROVIDER_OPENAI as STOCK_RESEARCH_PROVIDER_OPENAI,
    AgentModelCatalogEntry as StockResearchAgentModelCatalogEntry,
    AgentProviderCatalogEntry as StockResearchAgentProviderCatalogEntry,
    AgentRuntimeConfig as StockResearchAgentRuntimeConfig,
    build_chat_model,
    build_runtime_catalog,
    get_default_runtime_config,
    resolve_runtime_config,
)
from app.config.settings import get_settings

STOCK_RESEARCH_MAX_TOKENS = 16384
STOCK_RESEARCH_TEMPERATURE = 0.2


@lru_cache
def get_stock_research_runtime_catalog() -> (
    tuple[StockResearchAgentProviderCatalogEntry, ...]
):
    """Return the server-side stock-research runtime catalog."""
    settings = get_settings()
    return build_runtime_catalog(
        minimax_models=(
            StockResearchAgentModelCatalogEntry(
                model="MiniMax-M2.7-highspeed",
                is_default=True,
            ),
            StockResearchAgentModelCatalogEntry(
                model="MiniMax-M2.7",
                is_default=False,
            ),
        ),
        azure_models=(
            StockResearchAgentModelCatalogEntry(
                model=settings.AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT or "",
                is_default=True,
            ),
        ),
        openai_models=(
            StockResearchAgentModelCatalogEntry(
                model="gpt-5.2",
                reasoning_options=STOCK_RESEARCH_OPENAI_REASONING_OPTIONS,
                default_reasoning="high",
                is_default=True,
            ),
            StockResearchAgentModelCatalogEntry(
                model="gpt-5.4",
                reasoning_options=STOCK_RESEARCH_OPENAI_REASONING_OPTIONS,
                default_reasoning="high",
                is_default=False,
            ),
            StockResearchAgentModelCatalogEntry(
                model="gpt-5.4-mini",
                reasoning_options=STOCK_RESEARCH_OPENAI_REASONING_OPTIONS,
                default_reasoning="high",
                is_default=False,
            ),
            StockResearchAgentModelCatalogEntry(model="gpt-4.1"),
        ),
    )


def get_default_stock_research_runtime_config() -> StockResearchAgentRuntimeConfig:
    """Return the default runtime config exposed to callers."""
    return get_default_runtime_config(
        catalog=get_stock_research_runtime_catalog(),
        agent_label="stock-research",
    )


def resolve_stock_research_runtime_config(
    *,
    provider: str,
    model: str,
    reasoning: str | None = None,
) -> StockResearchAgentRuntimeConfig:
    """Validate and normalize one requested stock-research runtime config."""
    return resolve_runtime_config(
        catalog=get_stock_research_runtime_catalog(),
        provider=provider,
        model=model,
        reasoning=reasoning,
        agent_label="stock-research",
    )


def build_stock_research_model(
    runtime_config: StockResearchAgentRuntimeConfig | None = None,
) -> object:
    """Build the concrete LangChain chat model for one stock-research runtime."""
    resolved_config = runtime_config or get_default_stock_research_runtime_config()
    return build_chat_model(
        runtime_config=resolved_config,
        agent_label="stock-research",
        max_tokens=STOCK_RESEARCH_MAX_TOKENS,
        temperature=STOCK_RESEARCH_TEMPERATURE,
        streaming=False,
    )
