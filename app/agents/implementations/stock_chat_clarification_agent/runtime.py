"""Runtime helpers for stock-chat clarification execution."""

from __future__ import annotations

from functools import lru_cache

from app.agents.runtime import (
    AGENT_OPENAI_REASONING_OPTIONS as STOCK_CHAT_OPENAI_REASONING_OPTIONS,
)
from app.agents.runtime import (
    AGENT_PROVIDER_AZURA as STOCK_CHAT_PROVIDER_AZURA,
)
from app.agents.runtime import (
    AGENT_PROVIDER_MINIMAX as STOCK_CHAT_PROVIDER_MINIMAX,
)
from app.agents.runtime import (
    AGENT_PROVIDER_OPENAI as STOCK_CHAT_PROVIDER_OPENAI,
)
from app.agents.runtime import (
    AGENT_PROVIDER_ZAI as STOCK_CHAT_PROVIDER_ZAI,
)
from app.agents.runtime import (
    AgentModelCatalogEntry as StockChatModelCatalogEntry,
)
from app.agents.runtime import (
    AgentProviderCatalogEntry as StockChatProviderCatalogEntry,
)
from app.agents.runtime import (
    AgentRuntimeConfig as StockChatRuntimeConfig,
)
from app.agents.runtime import (
    build_chat_model,
    build_runtime_catalog,
    get_default_runtime_config,
    resolve_runtime_config,
)
from app.config.settings import get_settings

STOCK_CHAT_CLARIFICATION_MAX_TOKENS = 2048
STOCK_CHAT_CLARIFICATION_TEMPERATURE = 0.0


@lru_cache
def get_stock_chat_clarification_runtime_catalog() -> tuple[
    StockChatProviderCatalogEntry, ...
]:
    """Return the server-side stock-chat clarification runtime catalog."""
    settings = get_settings()
    return build_runtime_catalog(
        minimax_models=(
            StockChatModelCatalogEntry(
                model="MiniMax-M2.7-highspeed",
                is_default=True,
            ),
            StockChatModelCatalogEntry(
                model="MiniMax-M2.7",
                is_default=False,
            ),
        ),
        zai_models=(
            StockChatModelCatalogEntry(
                model="glm-5.1",
                is_default=True,
            ),
            StockChatModelCatalogEntry(
                model="glm-5-turbo",
                is_default=False,
            ),
        ),
        azure_models=(
            StockChatModelCatalogEntry(
                model=settings.AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT or "",
                is_default=True,
            ),
        ),
        openai_models=(
            StockChatModelCatalogEntry(
                model="gpt-5.4-mini",
                reasoning_options=STOCK_CHAT_OPENAI_REASONING_OPTIONS,
                default_reasoning="low",
                is_default=False,
            ),
            StockChatModelCatalogEntry(
                model="gpt-5.4",
                reasoning_options=STOCK_CHAT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=True,
            ),
            StockChatModelCatalogEntry(
                model="gpt-5.2",
                reasoning_options=STOCK_CHAT_OPENAI_REASONING_OPTIONS,
                default_reasoning="low",
                is_default=False,
            ),
            StockChatModelCatalogEntry(model="gpt-4.1"),
        ),
        default_provider=STOCK_CHAT_PROVIDER_OPENAI,
    )


def get_default_stock_chat_clarification_runtime_config() -> StockChatRuntimeConfig:
    """Return the default runtime config for stock-chat clarification."""
    return get_default_runtime_config(
        catalog=get_stock_chat_clarification_runtime_catalog(),
        agent_label="stock-chat clarification",
    )


def resolve_stock_chat_clarification_runtime_config(
    *,
    provider: str,
    model: str,
    reasoning: str | None = None,
) -> StockChatRuntimeConfig:
    """Validate and normalize one requested stock-chat clarification runtime."""
    return resolve_runtime_config(
        catalog=get_stock_chat_clarification_runtime_catalog(),
        provider=provider,
        model=model,
        reasoning=reasoning,
        agent_label="stock-chat clarification",
    )


def build_stock_chat_clarification_model(
    runtime_config: StockChatRuntimeConfig | None = None,
) -> object:
    """Build the concrete LangChain chat model for stock-chat clarification."""
    resolved_config = (
        runtime_config or get_default_stock_chat_clarification_runtime_config()
    )
    return build_chat_model(
        runtime_config=resolved_config,
        agent_label="stock-chat clarification",
        max_tokens=STOCK_CHAT_CLARIFICATION_MAX_TOKENS,
        temperature=STOCK_CHAT_CLARIFICATION_TEMPERATURE,
        streaming=False,
    )
