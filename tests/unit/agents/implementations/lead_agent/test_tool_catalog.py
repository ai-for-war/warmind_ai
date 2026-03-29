from __future__ import annotations

import app.agents.implementations.lead_agent.tool_catalog as tool_catalog_module


def test_tool_catalog_is_empty_until_new_lead_agent_tools_are_added() -> None:
    catalog = tool_catalog_module.get_lead_agent_selectable_tool_catalog()
    runtime_tools = tool_catalog_module.get_lead_agent_tools()

    assert catalog == []
    assert [tool.name for tool in runtime_tools] == ["load_skill"]


def test_tool_catalog_names_match_empty_catalog() -> None:
    assert tool_catalog_module.get_lead_agent_selectable_tool_names() == set()
