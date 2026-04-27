from __future__ import annotations

import os
from types import SimpleNamespace

from app.config.langsmith import configure_langsmith


def test_configure_langsmith_applies_enabled_settings(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_ENDPOINT", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)

    configure_langsmith(
        SimpleNamespace(
            LANGSMITH_TRACING=True,
            LANGSMITH_ENDPOINT="https://smith.example",
            LANGSMITH_API_KEY="test-key",
            LANGSMITH_PROJECT="worker-project",
        )
    )

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://smith.example"
    assert os.environ["LANGSMITH_API_KEY"] == "test-key"
    assert os.environ["LANGSMITH_PROJECT"] == "worker-project"


def test_configure_langsmith_disables_tracing(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    configure_langsmith(
        SimpleNamespace(
            LANGSMITH_TRACING=False,
            LANGSMITH_ENDPOINT=None,
            LANGSMITH_API_KEY=None,
            LANGSMITH_PROJECT=None,
        )
    )

    assert os.environ["LANGSMITH_TRACING"] == "false"
