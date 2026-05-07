from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.implementations.event_analyst.tools import (
    get_event_analyst_tool_surface,
)
from app.common.exceptions import AppException


def _tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def test_event_analyst_tool_surface_uses_only_search_and_fetch_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SimpleNamespace(
        get_tools=lambda tool_names: [
            _tool("search"),
            _tool("fetch_content"),
            _tool("secret_tool"),
        ]
    )
    monkeypatch.setattr(
        "app.agents.implementations.event_analyst.tools.get_mcp_tools_manager",
        lambda: manager,
    )

    surface = get_event_analyst_tool_surface()

    assert surface.search.name == "search"
    assert surface.fetch_content.name == "fetch_content"
    assert [tool.name for tool in surface.tools] == ["search", "fetch_content"]


def test_event_analyst_tool_surface_rejects_missing_required_research_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SimpleNamespace(get_tools=lambda tool_names: [_tool("search")])
    monkeypatch.setattr(
        "app.agents.implementations.event_analyst.tools.get_mcp_tools_manager",
        lambda: manager,
    )

    with pytest.raises(AppException) as exc_info:
        get_event_analyst_tool_surface()

    assert "fetch_content" in str(exc_info.value)
