"""Runtime configuration helpers for the configurable lead-agent."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from langchain_openai import AzureChatOpenAI, ChatOpenAI

from app.common.exceptions import AppException
from app.config.settings import get_settings
from app.infrastructure.llm.factory import (
    get_chat_azure_openai_legacy,
    get_chat_minimax,
    get_chat_openai,
    get_chat_openai_legacy,
)

LEAD_AGENT_PROVIDER_OPENAI = "openai"
LEAD_AGENT_PROVIDER_AZURA = "azura"
LEAD_AGENT_PROVIDER_MINIMAX = "minimax"
LEAD_AGENT_OPENAI_REASONING_OPTIONS = ("low", "medium", "high")


@dataclass(frozen=True)
class LeadAgentModelCatalogEntry:
    """One supported model choice for the lead-agent."""

    model: str
    reasoning_options: tuple[str, ...] = ()
    default_reasoning: str | None = None
    is_default: bool = False


@dataclass(frozen=True)
class LeadAgentProviderCatalogEntry:
    """One provider and its supported lead-agent models."""

    provider: str
    display_name: str
    models: tuple[LeadAgentModelCatalogEntry, ...]
    is_default: bool = False


@dataclass(frozen=True)
class LeadAgentRuntimeConfig:
    """Resolved runtime configuration for one lead-agent turn."""

    provider: str
    model: str
    reasoning: str | None = None


@lru_cache
def get_lead_agent_runtime_catalog() -> tuple[LeadAgentProviderCatalogEntry, ...]:
    """Return the server-side lead-agent runtime catalog."""
    settings = get_settings()
    providers: list[LeadAgentProviderCatalogEntry] = []

    azure_ready = all(
        [
            settings.AZURE_OPENAI_API_KEY,
            settings.AZURE_OPENAI_ENDPOINT,
            settings.AZURE_OPENAI_API_VERSION,
            settings.AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT,
        ]
    )

    if settings.MINIMAX_API_KEY:
        providers.append(
            LeadAgentProviderCatalogEntry(
                provider=LEAD_AGENT_PROVIDER_MINIMAX,
                display_name="MiniMax",
                models=(
                    LeadAgentModelCatalogEntry(
                        model="MiniMax-M2.7-highspeed",
                        is_default=True,
                    ),
                    LeadAgentModelCatalogEntry(
                        model="MiniMax-M2.7",
                        is_default=False,
                    ),
                ),
                is_default=True,
            )
        )

    if azure_ready:
        providers.append(
            LeadAgentProviderCatalogEntry(
                provider=LEAD_AGENT_PROVIDER_AZURA,
                display_name="Azure OpenAI (Legacy)",
                models=(
                    LeadAgentModelCatalogEntry(
                        model=settings.AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT or "",
                        is_default=True,
                    ),
                ),
                is_default=not providers,
            )
        )

    if settings.OPENAI_API_KEY:
        providers.append(
            LeadAgentProviderCatalogEntry(
                provider=LEAD_AGENT_PROVIDER_OPENAI,
                display_name="OpenAI",
                models=(
                    LeadAgentModelCatalogEntry(
                        model="gpt-5.2",
                        reasoning_options=LEAD_AGENT_OPENAI_REASONING_OPTIONS,
                        default_reasoning="medium",
                        is_default=True,
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
                is_default=not providers,
            )
        )

    return tuple(providers)


def get_default_lead_agent_runtime_config() -> LeadAgentRuntimeConfig:
    """Return the default runtime config exposed to callers."""
    provider_entry = _get_default_provider_entry()
    model_entry = _get_default_model_entry(provider_entry)
    return LeadAgentRuntimeConfig(
        provider=provider_entry.provider,
        model=model_entry.model,
        reasoning=model_entry.default_reasoning,
    )


def resolve_lead_agent_runtime_config(
    *,
    provider: str,
    model: str,
    reasoning: str | None = None,
) -> LeadAgentRuntimeConfig:
    """Validate and normalize one requested lead-agent runtime config."""
    provider_value = _normalize_optional_string(provider)
    model_value = _normalize_optional_string(model)
    reasoning_value = _normalize_optional_string(reasoning)
    catalog = get_lead_agent_runtime_catalog()
    if not catalog:
        raise AppException("No lead-agent providers are configured")

    if provider_value is None:
        raise AppException("Lead-agent provider is required")
    if model_value is None:
        raise AppException("Lead-agent model is required")

    provider_entry = _resolve_provider_entry(provider_value)

    model_entry = _resolve_model_entry(
        provider_entry=provider_entry,
        model=model_value,
    )
    resolved_reasoning = _resolve_reasoning(
        provider=provider_entry.provider,
        model_entry=model_entry,
        reasoning=reasoning_value,
    )

    return LeadAgentRuntimeConfig(
        provider=provider_entry.provider,
        model=model_entry.model,
        reasoning=resolved_reasoning,
    )


def build_lead_agent_model(
    runtime_config: LeadAgentRuntimeConfig | None = None,
) -> ChatOpenAI | AzureChatOpenAI:
    """Build the concrete LangChain chat model for one lead-agent runtime."""
    resolved_config = runtime_config or get_default_lead_agent_runtime_config()

    if resolved_config.provider == LEAD_AGENT_PROVIDER_AZURA:
        return get_chat_azure_openai_legacy(
            model=resolved_config.model,
            azure_deployment=resolved_config.model,
            max_tokens=16384,
        )

    if resolved_config.provider == LEAD_AGENT_PROVIDER_MINIMAX:
        return get_chat_minimax(
            model=resolved_config.model,
            max_tokens=16384,
        )

    if resolved_config.provider == LEAD_AGENT_PROVIDER_OPENAI:
        if resolved_config.reasoning is not None:
            return get_chat_openai(
                model=resolved_config.model,
                max_tokens=16384,
                reasoning_effort=resolved_config.reasoning,
            )
        return get_chat_openai_legacy(
            model=resolved_config.model,
            max_tokens=16384,
        )

    raise AppException(f"Unsupported lead-agent provider '{resolved_config.provider}'")


def _get_default_provider_entry() -> LeadAgentProviderCatalogEntry:
    catalog = get_lead_agent_runtime_catalog()
    if not catalog:
        raise AppException("No lead-agent providers are configured")

    return next((entry for entry in catalog if entry.is_default), catalog[0])


def _get_default_model_entry(
    provider_entry: LeadAgentProviderCatalogEntry,
) -> LeadAgentModelCatalogEntry:
    return next(
        (entry for entry in provider_entry.models if entry.is_default),
        provider_entry.models[0],
    )


def _resolve_provider_entry(provider: str) -> LeadAgentProviderCatalogEntry:
    catalog = get_lead_agent_runtime_catalog()
    for entry in catalog:
        if entry.provider == provider:
            return entry

    supported_providers = ", ".join(entry.provider for entry in catalog)
    raise AppException(
        f"Unsupported lead-agent provider '{provider}'. Supported providers: {supported_providers}"
    )


def _resolve_model_entry(
    *,
    provider_entry: LeadAgentProviderCatalogEntry,
    model: str,
) -> LeadAgentModelCatalogEntry:
    for entry in provider_entry.models:
        if entry.model == model:
            return entry

    supported_models = ", ".join(entry.model for entry in provider_entry.models)
    raise AppException(
        f"Unsupported lead-agent model '{model}' for provider '{provider_entry.provider}'. Supported models: {supported_models}"
    )


def _resolve_reasoning(
    *,
    provider: str,
    model_entry: LeadAgentModelCatalogEntry,
    reasoning: str | None,
) -> str | None:
    if not model_entry.reasoning_options:
        if reasoning is not None:
            raise AppException(
                f"Provider '{provider}' with model '{model_entry.model}' does not support reasoning selection"
            )
        return None

    if reasoning is None:
        raise AppException(
            f"Reasoning is required for provider '{provider}' and model '{model_entry.model}'"
        )

    if reasoning not in model_entry.reasoning_options:
        supported_reasoning = ", ".join(model_entry.reasoning_options)
        raise AppException(
            f"Unsupported reasoning '{reasoning}' for provider '{provider}' and model '{model_entry.model}'. Supported values: {supported_reasoning}"
        )

    return reasoning


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized_value = value.strip()
    return normalized_value or None
