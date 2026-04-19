from __future__ import annotations

import importlib
import sys
from types import ModuleType

from app.agents.implementations.lead_agent.state import LeadAgentState


def test_create_lead_agent_registers_skill_support_tool_surface(
    monkeypatch,
) -> None:
    checkpointer_module = ModuleType("app.infrastructure.langgraph.checkpointer")
    checkpointer_module.get_langgraph_checkpointer = lambda: object()
    monkeypatch.setitem(
        sys.modules,
        "app.infrastructure.langgraph.checkpointer",
        checkpointer_module,
    )
    sys.modules.pop("app.agents.implementations.lead_agent.agent", None)
    lead_agent_module = importlib.import_module(
        "app.agents.implementations.lead_agent.agent"
    )

    captured: dict[str, object] = {}
    fake_model = object()
    fake_checkpointer = object()
    fake_tools = [object()]
    fake_middleware = [object()]
    fake_prompt = "lead-agent-system-prompt"

    def _fake_create_agent(**kwargs):
        captured.update(kwargs)
        return "compiled-agent"

    monkeypatch.setattr(
        lead_agent_module,
        "build_lead_agent_model",
        lambda runtime_config=None: fake_model,
    )
    monkeypatch.setattr(
        lead_agent_module,
        "get_langgraph_checkpointer",
        lambda: fake_checkpointer,
    )
    monkeypatch.setattr(
        lead_agent_module,
        "create_agent",
        _fake_create_agent,
    )
    monkeypatch.setattr(
        lead_agent_module,
        "get_lead_agent_tools",
        lambda: fake_tools,
    )
    monkeypatch.setattr(
        lead_agent_module,
        "build_lead_agent_middleware",
        lambda model: fake_middleware if model is fake_model else [],
    )
    monkeypatch.setattr(
        lead_agent_module,
        "get_lead_agent_system_prompt",
        lambda *, subagent_enabled=False: (
            f"{fake_prompt}-subagent" if subagent_enabled else fake_prompt
        ),
    )

    compiled_agent = lead_agent_module.create_lead_agent()

    assert compiled_agent == "compiled-agent"
    assert captured["model"] is fake_model
    assert captured["tools"] is fake_tools
    assert captured["system_prompt"] == fake_prompt
    assert captured["middleware"] is fake_middleware
    assert captured["state_schema"] is LeadAgentState
    assert captured["checkpointer"] is fake_checkpointer


def test_create_lead_agent_can_render_subagent_enabled_base_prompt(
    monkeypatch,
) -> None:
    checkpointer_module = ModuleType("app.infrastructure.langgraph.checkpointer")
    checkpointer_module.get_langgraph_checkpointer = lambda: object()
    monkeypatch.setitem(
        sys.modules,
        "app.infrastructure.langgraph.checkpointer",
        checkpointer_module,
    )
    sys.modules.pop("app.agents.implementations.lead_agent.agent", None)
    lead_agent_module = importlib.import_module(
        "app.agents.implementations.lead_agent.agent"
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        lead_agent_module,
        "build_lead_agent_model",
        lambda runtime_config=None: object(),
    )
    monkeypatch.setattr(
        lead_agent_module,
        "get_langgraph_checkpointer",
        lambda: object(),
    )
    monkeypatch.setattr(
        lead_agent_module,
        "create_agent",
        lambda **kwargs: captured.update(kwargs) or "compiled-agent",
    )
    monkeypatch.setattr(
        lead_agent_module,
        "get_lead_agent_tools",
        lambda: [object()],
    )
    monkeypatch.setattr(
        lead_agent_module,
        "build_lead_agent_middleware",
        lambda model: [model],
    )
    monkeypatch.setattr(
        lead_agent_module,
        "get_lead_agent_system_prompt",
        lambda *, subagent_enabled=False: (
            "prompt-with-subagents" if subagent_enabled else "prompt-default"
        ),
    )

    compiled_agent = lead_agent_module.create_lead_agent(subagent_enabled=True)

    assert compiled_agent == "compiled-agent"
    assert captured["system_prompt"] == "prompt-with-subagents"
    assert len(captured["middleware"]) == 1
