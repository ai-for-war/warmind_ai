"""LangSmith tracing configuration helpers."""

from __future__ import annotations

import os

from app.config.settings import Settings, get_settings


def configure_langsmith(settings: Settings | None = None) -> None:
    """Apply LangSmith tracing settings to the current process environment."""
    resolved_settings = settings or get_settings()

    os.environ["LANGSMITH_TRACING"] = (
        "true" if resolved_settings.LANGSMITH_TRACING else "false"
    )

    if resolved_settings.LANGSMITH_ENDPOINT:
        os.environ["LANGSMITH_ENDPOINT"] = resolved_settings.LANGSMITH_ENDPOINT

    if resolved_settings.LANGSMITH_API_KEY:
        os.environ["LANGSMITH_API_KEY"] = resolved_settings.LANGSMITH_API_KEY

    if resolved_settings.LANGSMITH_PROJECT:
        os.environ["LANGSMITH_PROJECT"] = resolved_settings.LANGSMITH_PROJECT
