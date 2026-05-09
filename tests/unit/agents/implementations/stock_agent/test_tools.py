from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import ToolMessage

from app.agents.implementations.stock_agent.tools import (
    STOCK_AGENT_INTERNAL_TOOLS,
    _delegate_tasks_result,
    _load_skill_command,
)


def _skill(
    *,
    skill_id: str = "web-research",
    allowed_tool_names: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        _id=f"{skill_id}-id",
        skill_id=skill_id,
        name="Web Research",
        description="Research web sources",
        activation_prompt="Use the web skill",
        allowed_tool_names=allowed_tool_names or ["search_docs"],
        version="2.1.0",
        created_by="user-1",
        organization_id="org-1",
    )


def _runtime(
    *,
    state: dict[str, object] | None = None,
    tool_call_id: str = "tool-call-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        state=state
        or {
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
            "enabled_skill_ids": ["web-research"],
            "loaded_skills": ["sales-playbook"],
        },
        tool_call_id=tool_call_id,
    )


@pytest.mark.asyncio
async def test_load_skill_command_updates_runtime_state_for_enabled_skill() -> None:
    skill_access_resolver = SimpleNamespace(
        resolve_enabled_skill_for_caller=AsyncMock(
            return_value=_skill(
                allowed_tool_names=["search_docs", "search_docs", " summarize "]
            )
        )
    )

    command = await _load_skill_command(
        skill_id=" web-research ",
        runtime=_runtime(),
        skill_access_resolver=skill_access_resolver,
    )

    update = command.update
    assert isinstance(update, dict)
    assert update["active_skill_id"] == "web-research"
    assert update["loaded_skills"] == ["sales-playbook", "web-research"]
    assert update["allowed_tool_names"] == ["search_docs", "summarize"]
    assert update["active_skill_version"] == "2.1.0"
    message = update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.content == "Loaded skill 'web-research' (v2.1.0)."
    assert message.tool_call_id == "tool-call-1"
    skill_access_resolver.resolve_enabled_skill_for_caller.assert_awaited_once_with(
        user_id="user-1",
        organization_id="org-1",
        skill_id="web-research",
    )


@pytest.mark.asyncio
async def test_load_skill_command_rejects_disabled_skill_without_repo_lookup() -> None:
    skill_access_resolver = SimpleNamespace(
        resolve_enabled_skill_for_caller=AsyncMock()
    )

    command = await _load_skill_command(
        skill_id="finance-ops",
        runtime=_runtime(
            state={
                "messages": [],
                "user_id": "user-1",
                "organization_id": "org-1",
                "enabled_skill_ids": ["web-research"],
            }
        ),
        skill_access_resolver=skill_access_resolver,
    )

    update = command.update
    assert isinstance(update, dict)
    assert list(update.keys()) == ["messages"]
    message = update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.content == "Skill 'finance-ops' is not available for this thread."
    skill_access_resolver.resolve_enabled_skill_for_caller.assert_not_awaited()


@pytest.mark.asyncio
async def test_delegate_tasks_result_uses_supplied_executor() -> None:
    executor = SimpleNamespace(
        execute=AsyncMock(
            return_value={
                "status": "completed",
                "worker_timeout_seconds": 30,
                "result": {
                    "status": "completed",
                    "summary": "done",
                },
            }
        )
    )

    result = await _delegate_tasks_result(
        task={
            "agent_id": "general_worker",
            "objective": "Investigate the runtime",
        },
        runtime=_runtime(),
        executor=executor,
    )

    assert result["status"] == "completed"
    executor.execute.assert_awaited_once_with(
        {
            "agent_id": "general_worker",
            "objective": "Investigate the runtime",
        }
    )


def test_stock_agent_tools_register_internal_load_skill_tool() -> None:
    assert [tool.name for tool in STOCK_AGENT_INTERNAL_TOOLS] == [
        "load_skill",
        "delegate_tasks",
    ]


def test_delegate_tasks_tool_description_documents_agent_id_contract() -> None:
    delegate_tool = STOCK_AGENT_INTERNAL_TOOLS[1]

    assert "agent_id" in delegate_tool.description
    assert "objective" in delegate_tool.description
    assert "context" in delegate_tool.description
    assert "general_worker" in delegate_tool.description
    assert "event_analyst" in delegate_tool.description
    assert "technical_analyst" in delegate_tool.description
    assert "fundamental_analyst" in delegate_tool.description
    assert "business profile" in delegate_tool.description
    assert "valuation-ratio evidence" in delegate_tool.description
