"""LLM factory for creating language model instances."""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config.settings import get_settings


def get_chat_openai(
    model: str = "gpt-5.2",
    temperature: float = 0.7,
    streaming: bool = True,
    max_tokens: int = 2048,
    base_url: str | None = None,
) -> ChatOpenAI:
    """Create ChatOpenAI instance with configurable parameters.

    Args:
        model: OpenAI model name. Defaults to "gpt-4o-mini".
        temperature: Sampling temperature. Defaults to 0.7.
        streaming: Enable streaming responses. Defaults to True.
        base_url: Custom API base URL. Defaults to settings value or None.

    Returns:
        ChatOpenAI instance configured with the specified parameters.
    """
    settings = get_settings()
    api_base = base_url or settings.OPENAI_API_BASE
    return ChatOpenAI(
        reasoning_effort="high",
        store=False,
        api_key=settings.OPENAI_API_KEY,
        base_url=api_base,
        model=model,
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
