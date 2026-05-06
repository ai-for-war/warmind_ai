"""Runtime helpers for sandbox trade-agent execution."""

from __future__ import annotations

from functools import lru_cache

from app.agents.runtime import (
    AGENT_OPENAI_REASONING_OPTIONS as SANDBOX_TRADE_OPENAI_REASONING_OPTIONS,
    AGENT_PROVIDER_OPENAI as SANDBOX_TRADE_PROVIDER_OPENAI,
    AgentModelCatalogEntry as SandboxTradeAgentModelCatalogEntry,
    AgentProviderCatalogEntry as SandboxTradeAgentProviderCatalogEntry,
    AgentRuntimeConfig as SandboxTradeAgentRuntimeConfig,
    build_chat_model,
    build_runtime_catalog,
    get_default_runtime_config,
    resolve_runtime_config,
)

SANDBOX_TRADE_MAX_TOKENS = 4096
SANDBOX_TRADE_TEMPERATURE = 0.1


@lru_cache
def get_sandbox_trade_runtime_catalog() -> (
    tuple[SandboxTradeAgentProviderCatalogEntry, ...]
):
    """Return the server-side sandbox trade-agent runtime catalog."""
    return build_runtime_catalog(
        openai_models=(
            SandboxTradeAgentModelCatalogEntry(
                model="gpt-5.4",
                reasoning_options=SANDBOX_TRADE_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=True,
            ),
            SandboxTradeAgentModelCatalogEntry(
                model="gpt-5.4-mini",
                reasoning_options=SANDBOX_TRADE_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            SandboxTradeAgentModelCatalogEntry(model="gpt-4.1"),
        ),
        default_provider=SANDBOX_TRADE_PROVIDER_OPENAI,
    )


def get_default_sandbox_trade_runtime_config() -> SandboxTradeAgentRuntimeConfig:
    """Return the default runtime config exposed to sandbox trade sessions."""
    return get_default_runtime_config(
        catalog=get_sandbox_trade_runtime_catalog(),
        agent_label="sandbox-trade-agent",
    )


def resolve_sandbox_trade_runtime_config(
    *,
    provider: str,
    model: str,
    reasoning: str | None = None,
) -> SandboxTradeAgentRuntimeConfig:
    """Validate and normalize one requested sandbox trade runtime config."""
    return resolve_runtime_config(
        catalog=get_sandbox_trade_runtime_catalog(),
        provider=provider,
        model=model,
        reasoning=reasoning,
        agent_label="sandbox-trade-agent",
    )


def build_sandbox_trade_model(
    runtime_config: SandboxTradeAgentRuntimeConfig | None = None,
) -> object:
    """Build the concrete LangChain chat model for one sandbox trade run."""
    resolved_config = runtime_config or get_default_sandbox_trade_runtime_config()
    return build_chat_model(
        runtime_config=resolved_config,
        agent_label="sandbox-trade-agent",
        max_tokens=SANDBOX_TRADE_MAX_TOKENS,
        temperature=SANDBOX_TRADE_TEMPERATURE,
        streaming=False,
    )
