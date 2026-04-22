"""Shared runtime catalog and model-builder helpers for agent runtimes."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_openai import AzureChatOpenAI, ChatOpenAI

from app.common.exceptions import AppException
from app.config.settings import get_settings
from app.infrastructure.llm.factory import (
    get_chat_azure_openai_legacy,
    get_chat_minimax,
    get_chat_openai,
    get_chat_openai_legacy,
)

AGENT_PROVIDER_OPENAI = "openai"
AGENT_PROVIDER_AZURA = "azura"
AGENT_PROVIDER_MINIMAX = "minimax"
AGENT_OPENAI_REASONING_OPTIONS = ("low", "medium", "high")


@dataclass(frozen=True)
class AgentModelCatalogEntry:
    """One supported model choice for an agent runtime."""

    model: str
    reasoning_options: tuple[str, ...] = ()
    default_reasoning: str | None = None
    is_default: bool = False


@dataclass(frozen=True)
class AgentProviderCatalogEntry:
    """One provider and its supported runtime models."""

    provider: str
    display_name: str
    models: tuple[AgentModelCatalogEntry, ...]
    is_default: bool = False


@dataclass(frozen=True)
class AgentRuntimeConfig:
    """Resolved runtime configuration for one agent run."""

    provider: str
    model: str
    reasoning: str | None = None


def build_runtime_catalog(
    *,
    openai_models: tuple[AgentModelCatalogEntry, ...] = (),
    azure_models: tuple[AgentModelCatalogEntry, ...] = (),
    minimax_models: tuple[AgentModelCatalogEntry, ...] = (),
    openai_display_name: str = "OpenAI",
    azure_display_name: str = "Azure OpenAI (Legacy)",
    minimax_display_name: str = "MiniMax",
) -> tuple[AgentProviderCatalogEntry, ...]:
    """Build one provider catalog from the currently configured backends."""
    settings = get_settings()
    providers: list[AgentProviderCatalogEntry] = []

    if settings.MINIMAX_API_KEY and minimax_models:
        providers.append(
            AgentProviderCatalogEntry(
                provider=AGENT_PROVIDER_MINIMAX,
                display_name=minimax_display_name,
                models=minimax_models,
                is_default=True,
            )
        )

    if _is_azure_legacy_ready() and azure_models:
        providers.append(
            AgentProviderCatalogEntry(
                provider=AGENT_PROVIDER_AZURA,
                display_name=azure_display_name,
                models=azure_models,
                is_default=not providers,
            )
        )

    if settings.OPENAI_API_KEY and openai_models:
        providers.append(
            AgentProviderCatalogEntry(
                provider=AGENT_PROVIDER_OPENAI,
                display_name=openai_display_name,
                models=openai_models,
                is_default=not providers,
            )
        )

    return tuple(providers)


def get_default_runtime_config(
    *,
    catalog: tuple[AgentProviderCatalogEntry, ...],
    agent_label: str,
) -> AgentRuntimeConfig:
    """Return the default runtime config for one agent runtime catalog."""
    provider_entry = _get_default_provider_entry(catalog=catalog, agent_label=agent_label)
    model_entry = _get_default_model_entry(provider_entry)
    return AgentRuntimeConfig(
        provider=provider_entry.provider,
        model=model_entry.model,
        reasoning=model_entry.default_reasoning,
    )


def resolve_runtime_config(
    *,
    catalog: tuple[AgentProviderCatalogEntry, ...],
    provider: str,
    model: str,
    reasoning: str | None = None,
    agent_label: str,
) -> AgentRuntimeConfig:
    """Validate and normalize one requested agent runtime config."""
    provider_value = _normalize_optional_string(provider)
    model_value = _normalize_optional_string(model)
    reasoning_value = _normalize_optional_string(reasoning)
    if not catalog:
        raise AppException(f"No {agent_label} providers are configured")

    if provider_value is None:
        raise AppException(f"{_format_agent_label(agent_label)} provider is required")
    if model_value is None:
        raise AppException(f"{_format_agent_label(agent_label)} model is required")

    provider_entry = _resolve_provider_entry(
        catalog=catalog,
        provider=provider_value,
        agent_label=agent_label,
    )
    model_entry = _resolve_model_entry(
        provider_entry=provider_entry,
        model=model_value,
        agent_label=agent_label,
    )
    resolved_reasoning = _resolve_reasoning(
        provider=provider_entry.provider,
        model_entry=model_entry,
        reasoning=reasoning_value,
    )

    return AgentRuntimeConfig(
        provider=provider_entry.provider,
        model=model_entry.model,
        reasoning=resolved_reasoning,
    )


def build_chat_model(
    *,
    runtime_config: AgentRuntimeConfig,
    agent_label: str,
    max_tokens: int,
    temperature: float = 0.7,
    streaming: bool = True,
) -> ChatOpenAI | AzureChatOpenAI:
    """Build the concrete LangChain chat model for one agent runtime."""
    if runtime_config.provider == AGENT_PROVIDER_AZURA:
        return get_chat_azure_openai_legacy(
            model=runtime_config.model,
            azure_deployment=runtime_config.model,
            max_tokens=max_tokens,
            temperature=temperature,
            streaming=streaming,
        )

    if runtime_config.provider == AGENT_PROVIDER_MINIMAX:
        return get_chat_minimax(
            model=runtime_config.model,
            max_tokens=max_tokens,
            temperature=temperature,
            streaming=streaming,
        )

    if runtime_config.provider == AGENT_PROVIDER_OPENAI:
        if runtime_config.reasoning is not None:
            return get_chat_openai(
                model=runtime_config.model,
                max_tokens=max_tokens,
                temperature=temperature,
                streaming=streaming,
                reasoning_effort=runtime_config.reasoning,
            )
        return get_chat_openai_legacy(
            model=runtime_config.model,
            max_tokens=max_tokens,
            temperature=temperature,
            streaming=streaming,
        )

    raise AppException(
        f"Unsupported {agent_label} provider '{runtime_config.provider}'"
    )


def _is_azure_legacy_ready() -> bool:
    settings = get_settings()
    return all(
        [
            settings.AZURE_OPENAI_API_KEY,
            settings.AZURE_OPENAI_ENDPOINT,
            settings.AZURE_OPENAI_API_VERSION,
            settings.AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT,
        ]
    )


def _get_default_provider_entry(
    *,
    catalog: tuple[AgentProviderCatalogEntry, ...],
    agent_label: str,
) -> AgentProviderCatalogEntry:
    if not catalog:
        raise AppException(f"No {agent_label} providers are configured")

    return next((entry for entry in catalog if entry.is_default), catalog[0])


def _get_default_model_entry(
    provider_entry: AgentProviderCatalogEntry,
) -> AgentModelCatalogEntry:
    return next(
        (entry for entry in provider_entry.models if entry.is_default),
        provider_entry.models[0],
    )


def _resolve_provider_entry(
    *,
    catalog: tuple[AgentProviderCatalogEntry, ...],
    provider: str,
    agent_label: str,
) -> AgentProviderCatalogEntry:
    for entry in catalog:
        if entry.provider == provider:
            return entry

    supported_providers = ", ".join(entry.provider for entry in catalog)
    raise AppException(
        f"Unsupported {agent_label} provider '{provider}'. Supported providers: {supported_providers}"
    )


def _resolve_model_entry(
    *,
    provider_entry: AgentProviderCatalogEntry,
    model: str,
    agent_label: str,
) -> AgentModelCatalogEntry:
    for entry in provider_entry.models:
        if entry.model == model:
            return entry

    supported_models = ", ".join(entry.model for entry in provider_entry.models)
    raise AppException(
        f"Unsupported {agent_label} model '{model}' for provider '{provider_entry.provider}'. Supported models: {supported_models}"
    )


def _resolve_reasoning(
    *,
    provider: str,
    model_entry: AgentModelCatalogEntry,
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


def _format_agent_label(agent_label: str) -> str:
    return agent_label[:1].upper() + agent_label[1:]
