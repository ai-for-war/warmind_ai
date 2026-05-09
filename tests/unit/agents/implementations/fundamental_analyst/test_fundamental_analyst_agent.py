from __future__ import annotations

from app.agents.implementations.fundamental_analyst import agent as agent_module
from app.agents.implementations.fundamental_analyst.validation import (
    FundamentalAnalystOutput,
)
from app.agents.runtime import AgentRuntimeConfig


def test_create_fundamental_analyst_agent_registers_bounded_tool_surface(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    fake_model = object()
    fake_middleware = [object()]

    monkeypatch.setattr(
        agent_module,
        "build_fundamental_analyst_model",
        lambda runtime_config: fake_model,
    )
    monkeypatch.setattr(
        agent_module,
        "build_fundamental_analyst_middleware",
        lambda model: fake_middleware if model is fake_model else [],
    )
    monkeypatch.setattr(
        agent_module,
        "create_agent",
        lambda **kwargs: captured.update(kwargs) or "compiled-agent",
    )

    compiled_agent = agent_module.create_fundamental_analyst_agent(
        AgentRuntimeConfig(
            provider="openai",
            model="gpt-5.2",
            reasoning="medium",
        )
    )

    assert compiled_agent == "compiled-agent"
    assert captured["model"] is fake_model
    assert [tool.name for tool in captured["tools"]] == [
        "load_company_profile",
        "load_income_statement",
        "load_balance_sheet",
        "load_cash_flow",
        "load_financial_ratios",
    ]
    assert captured["middleware"] is fake_middleware
    assert captured["response_format"] is FundamentalAnalystOutput
    assert "fundamental analyst" in str(captured["system_prompt"]).lower()
