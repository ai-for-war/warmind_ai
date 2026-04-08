from __future__ import annotations

from types import SimpleNamespace

import app.agents.implementations.lead_agent.tool_catalog as tool_catalog_module


def test_tool_catalog_exposes_research_tools_when_available(monkeypatch) -> None:
    search_tool = SimpleNamespace(name="search")
    fetch_content_tool = SimpleNamespace(name="fetch_content")
    monkeypatch.setattr(
        tool_catalog_module,
        "get_mcp_tools_manager",
        lambda: SimpleNamespace(
            get_tools=lambda tool_names=None: [search_tool, fetch_content_tool]
        ),
    )

    catalog = tool_catalog_module.get_lead_agent_selectable_tool_catalog()
    runtime_tools = tool_catalog_module.get_lead_agent_tools()

    assert [tool.tool_name for tool in catalog] == ["search", "fetch_content"]
    assert catalog[0].display_name == "Web Search"
    assert catalog[1].display_name == "Fetch Web Content"
    assert [tool.name for tool in runtime_tools] == [
        "load_skill",
        "delegate_tasks",
        "search",
        "fetch_content",
    ]


def test_tool_catalog_is_empty_when_research_tools_are_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        tool_catalog_module,
        "get_mcp_tools_manager",
        lambda: SimpleNamespace(get_tools=lambda tool_names=None: []),
    )

    assert tool_catalog_module.get_lead_agent_selectable_tool_catalog() == []
    assert tool_catalog_module.get_lead_agent_selectable_tool_names() == set()
    assert [tool.name for tool in tool_catalog_module.get_lead_agent_tools()] == [
        "load_skill",
        "delegate_tasks",
    ]


def test_tool_catalog_exposes_only_available_research_tools(monkeypatch) -> None:
    search_tool = SimpleNamespace(name="search")
    monkeypatch.setattr(
        tool_catalog_module,
        "get_mcp_tools_manager",
        lambda: SimpleNamespace(get_tools=lambda tool_names=None: [search_tool]),
    )

    catalog = tool_catalog_module.get_lead_agent_selectable_tool_catalog()
    runtime_tools = tool_catalog_module.get_lead_agent_tools()

    assert [tool.tool_name for tool in catalog] == ["search"]
    assert tool_catalog_module.get_lead_agent_selectable_tool_names() == {"search"}
    assert [tool.name for tool in runtime_tools] == [
        "load_skill",
        "delegate_tasks",
        "search",
    ]
