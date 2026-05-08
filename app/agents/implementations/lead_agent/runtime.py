"""Runtime configuration helpers for the configurable lead-agent."""

from __future__ import annotations

from functools import lru_cache

from app.agents.runtime import (
    AGENT_OPENAI_REASONING_OPTIONS as LEAD_AGENT_OPENAI_REASONING_OPTIONS,
)
from app.agents.runtime import (
    AGENT_PROVIDER_AZURA as LEAD_AGENT_PROVIDER_AZURA,
)
from app.agents.runtime import (
    AGENT_PROVIDER_MINIMAX as LEAD_AGENT_PROVIDER_MINIMAX,
)
from app.agents.runtime import (
    AGENT_PROVIDER_OPENAI as LEAD_AGENT_PROVIDER_OPENAI,
)
from app.agents.runtime import (
    AGENT_PROVIDER_ZAI as LEAD_AGENT_PROVIDER_ZAI,
)
from app.agents.runtime import (
    AgentModelCatalogEntry as LeadAgentModelCatalogEntry,
)
from app.agents.runtime import (
    AgentProviderCatalogEntry as LeadAgentProviderCatalogEntry,
)
from app.agents.runtime import (
    AgentRuntimeConfig as LeadAgentRuntimeConfig,
)
from app.agents.runtime import (
    build_chat_model,
    build_runtime_catalog,
    get_default_runtime_config,
    resolve_runtime_config,
)
from app.config.settings import get_settings


@lru_cache
def get_lead_agent_runtime_catalog() -> tuple[LeadAgentProviderCatalogEntry, ...]:
    """Return the server-side lead-agent runtime catalog."""
    settings = get_settings()
    return build_runtime_catalog(
        minimax_models=(
            LeadAgentModelCatalogEntry(
                model="MiniMax-M2.7-highspeed",
                is_default=True,
            ),
            LeadAgentModelCatalogEntry(
                model="MiniMax-M2.7",
                is_default=False,
            ),
        ),
        zai_models=(
            LeadAgentModelCatalogEntry(
                model="glm-5.1",
                is_default=False,
            ),
        ),
        azure_models=(
            LeadAgentModelCatalogEntry(
                model=settings.AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT or "",
                is_default=True,
            ),
        ),
        openai_models=(
            LeadAgentModelCatalogEntry(
                model="gpt-5.5",
                reasoning_options=LEAD_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=True,
            ),
            LeadAgentModelCatalogEntry(
                model="gpt-5.2",
                reasoning_options=LEAD_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            LeadAgentModelCatalogEntry(
                model="gpt-5.1",
                reasoning_options=LEAD_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            LeadAgentModelCatalogEntry(
                model="gpt-5.4",
                reasoning_options=LEAD_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            LeadAgentModelCatalogEntry(
                model="gpt-5.4-mini",
                reasoning_options=LEAD_AGENT_OPENAI_REASONING_OPTIONS,
                default_reasoning="medium",
                is_default=False,
            ),
            LeadAgentModelCatalogEntry(model="gpt-4.1"),
        ),
        default_provider=LEAD_AGENT_PROVIDER_OPENAI,
    )


def get_default_lead_agent_runtime_config() -> LeadAgentRuntimeConfig:
    """Return the default runtime config exposed to callers."""
    return get_default_runtime_config(
        catalog=get_lead_agent_runtime_catalog(),
        agent_label="lead-agent",
    )


def resolve_lead_agent_runtime_config(
    *,
    provider: str,
    model: str,
    reasoning: str | None = None,
) -> LeadAgentRuntimeConfig:
    """Validate and normalize one requested lead-agent runtime config."""
    return resolve_runtime_config(
        catalog=get_lead_agent_runtime_catalog(),
        provider=provider,
        model=model,
        reasoning=reasoning,
        agent_label="lead-agent",
    )


def build_lead_agent_model(
    runtime_config: LeadAgentRuntimeConfig | None = None,
) -> object:
    """Build the concrete LangChain chat model for one lead-agent runtime."""
    resolved_config = runtime_config or get_default_lead_agent_runtime_config()
    return build_chat_model(
        runtime_config=resolved_config,
        agent_label="lead-agent",
        max_tokens=16384,
    )
