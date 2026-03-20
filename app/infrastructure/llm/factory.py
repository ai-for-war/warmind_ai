"""LLM factory for creating language model instances."""

from functools import lru_cache

from langchain_openai import AzureChatOpenAI, ChatOpenAI

from app.config.settings import get_settings


def get_chat_openai(
    model: str = "gpt-5.2",
    temperature: float = 0.7,
    streaming: bool = True,
    max_tokens: int = 2048,
    base_url: str | None = None,
    reasoning_effort: str | None = "high",
) -> ChatOpenAI:
    """Create ChatOpenAI instance with configurable parameters.

    Args:
        model: OpenAI model name. Defaults to "gpt-5.2".
        temperature: Sampling temperature. Defaults to 0.7.
        streaming: Enable streaming responses. Defaults to True.
        max_tokens: Maximum number of tokens to generate. Defaults to 2048.
        base_url: Custom API base URL. Defaults to settings value or None.
        reasoning_effort: OpenAI reasoning effort level. Defaults to "high".

    Returns:
        ChatOpenAI instance configured with the specified parameters.
    """
    settings = get_settings()
    api_base = base_url or settings.OPENAI_API_BASE
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required")

    return ChatOpenAI(
        reasoning_effort=reasoning_effort,
        store=False,
        api_key=settings.OPENAI_API_KEY,
        base_url=api_base,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        streaming=streaming,
    )


def get_chat_openai_legacy(
    model: str = "gpt-4.1",
    temperature: float = 0.7,
    streaming: bool = True,
    max_tokens: int = 2048,
    base_url: str | None = None,
) -> ChatOpenAI:
    """Create ChatOpenAI legacy instance with configurable parameters.

    Args:
        model: OpenAI model name. Defaults to "gpt-4.1".
        temperature: Sampling temperature. Defaults to 0.7.
        streaming: Enable streaming responses. Defaults to True.
        max_tokens: Maximum number of tokens to generate. Defaults to 2048.
        base_url: Custom API base URL. Defaults to settings value or None.

    Returns:
        ChatOpenAI instance configured with the specified parameters.
    """
    settings = get_settings()
    api_base = base_url or settings.OPENAI_API_BASE
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required")

    return ChatOpenAI(
        store=False,
        api_key=settings.OPENAI_API_KEY,
        base_url=api_base,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        streaming=streaming,
    )


def get_chat_azure_openai_legacy(
    model: str | None = None,
    temperature: float = 0.7,
    streaming: bool = True,
    max_tokens: int = 2048,
    api_version: str | None = None,
    azure_deployment: str | None = None,
) -> AzureChatOpenAI:
    """Create AzureChatOpenAI legacy instance with configurable parameters."""
    settings = get_settings()
    deployment = azure_deployment or settings.AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT
    resolved_model = model or deployment

    return AzureChatOpenAI(
        store=False,
        api_key=settings.AZURE_OPENAI_API_KEY,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_version=api_version or settings.AZURE_OPENAI_API_VERSION,
        azure_deployment=deployment,
        model=resolved_model,
        max_tokens=max_tokens,
        temperature=temperature,
        streaming=streaming,
    )


@lru_cache
def get_default_chat_openai() -> ChatOpenAI:
    """Get singleton ChatOpenAI instance with default settings.

    Returns:
        Cached ChatOpenAI instance.
    """
    return get_chat_openai()
