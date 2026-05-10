"""Runtime configuration helpers for the configurable stock-agent."""

from __future__ import annotations

from functools import lru_cache

from app.agents.runtime import (
    AGENT_OPENAI_REASONING_OPTIONS as STOCK_AGENT_OPENAI_REASONING_OPTIONS,
)
from app.agents.runtime import (
    AGENT_PROVIDER_AZURA as STOCK_AGENT_PROVIDER_AZURA,
)
from app.agents.runtime import (
    AGENT_PROVIDER_MINIMAX as STOCK_AGENT_PROVIDER_MINIMAX,
)
from app.agents.runtime import (
    AGENT_PROVIDER_OPENAI as STOCK_AGENT_PROVIDER_OPENAI,
)
from app.agents.runtime import (
    AGENT_PROVIDER_ZAI as STOCK_AGENT_PROVIDER_ZAI,
)
from app.agents.runtime import (
    AgentModelCatalogEntry as StockAgentModelCatalogEntry,
)
from app.agents.runtime import (
    AgentProviderCatalogEntry as StockAgentProviderCatalogEntry,
)
from app.agents.runtime import (
    AgentRuntimeConfig as StockAgentRuntimeConfig,
)
from app.agents.runtime import (
    build_chat_model,
    build_runtime_catalog,
    get_default_runtime_config,
    resolve_runtime_config,
)
from app.config.settings import get_settings


@lru_cache
def get_stock_agent_runtime_catalog() -> tuple[StockAgentProviderCatalogEntry, ...]:
    """Return the server-side stock-agent runtime catalog."""
    settings = get_settings()
    return build_runtime_catalog(
        minimax_models=(
            StockAgentModelCatalogEntry(
                model="MiniMax-M2.7-highspeed",
                is_default=True,
            ),
            StockAgentModelCatalogEntry(
                model="MiniMax-M2.7",
                is_default=False,
            ),
        ),
        zai_models=(
            StockAgentModelCatalogEntry(
                model="glm-5.1",
                is_default=False,
            ),
        ),
        azure_models=(
            StockAgentModelCatalogEntry(
                model=settings.AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT or "",
                is_default=True,
            ),
        ),
        openai_models=(
            StockAgentModelCatalogEntry(
                model="gpt-5.5",
                reasoning_options=STOCK_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=True,
            ),
            StockAgentModelCatalogEntry(
                model="gpt-5.5-fast",
                reasoning_options=STOCK_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            StockAgentModelCatalogEntry(
                model="gpt-5.2",
                reasoning_options=STOCK_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            StockAgentModelCatalogEntry(
                model="gpt-5.1",
                reasoning_options=STOCK_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            StockAgentModelCatalogEntry(
                model="gpt-5.4",
                reasoning_options=STOCK_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            StockAgentModelCatalogEntry(
                model="gpt-5.4-mini",
                reasoning_options=STOCK_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            StockAgentModelCatalogEntry(model="gpt-4.1"),
        ),
        default_provider=STOCK_AGENT_PROVIDER_OPENAI,
    )


def get_default_stock_agent_runtime_config() -> StockAgentRuntimeConfig:
    """Return the default runtime config exposed to callers."""
    return get_default_runtime_config(
        catalog=get_stock_agent_runtime_catalog(),
        agent_label="stock-agent",
    )


def resolve_stock_agent_runtime_config(
    *,
    provider: str,
    model: str,
    reasoning: str | None = None,
) -> StockAgentRuntimeConfig:
    """Validate and normalize one requested stock-agent runtime config."""
    return resolve_runtime_config(
        catalog=get_stock_agent_runtime_catalog(),
        provider=provider,
        model=model,
        reasoning=reasoning,
        agent_label="stock-agent",
    )


def build_stock_agent_model(
    runtime_config: StockAgentRuntimeConfig | None = None,
) -> object:
    """Build the concrete LangChain chat model for one stock-agent runtime."""
    resolved_config = runtime_config or get_default_stock_agent_runtime_config()
    return build_chat_model(
        runtime_config=resolved_config,
        agent_label="stock-agent",
        max_tokens=8192,
    )
