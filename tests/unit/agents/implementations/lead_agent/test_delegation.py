from __future__ import annotations

import asyncio

import pytest

from app.agents.implementations.lead_agent.delegation import (
    DELEGATION_STATUS_COMPLETED,
    DELEGATION_STATUS_FAILED,
    DELEGATION_STATUS_REJECTED,
    DelegatedTaskInput,
    LeadAgentDelegationExecutor,
    WORKER_ORCHESTRATION_MODE,
    WORKER_STATUS_FAILED,
)


class _FakeWorkerAgent:
    def __init__(self, *, delay_seconds: float = 0.01) -> None:
        self.delay_seconds = delay_seconds
        self.calls: list[dict[str, object]] = []
        self.active_calls = 0
        self.max_active_calls = 0

    async def ainvoke(self, payload: dict[str, object], config: dict[str, object]):
        self.calls.append({"payload": payload, "config": config})
        content = str(payload["messages"][0]["content"])
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            await asyncio.sleep(self.delay_seconds)
            if "FAIL_WORKER" in content:
                raise RuntimeError("worker exploded")
            return {
                "messages": [
                    {"role": "assistant", "content": f"Completed {content.splitlines()[0]}"}
                ]
            }
        finally:
            self.active_calls -= 1


def _parent_state(*, delegation_depth: int = 0) -> dict[str, object]:
    return {
        "messages": [{"role": "user", "content": "Parent request"}],
        "user_id": "user-1",
        "organization_id": "org-1",
        "runtime_provider": "openai",
        "runtime_model": "gpt-5.2",
        "runtime_reasoning": "medium",
        "enabled_skill_ids": ["web-research", "workspace-analytics"],
        "delegation_depth": delegation_depth,
    }


@pytest.mark.asyncio
async def test_delegation_executor_builds_isolated_worker_payload() -> None:
    worker_agent = _FakeWorkerAgent()
    executor = LeadAgentDelegationExecutor(
        parent_state=_parent_state(),
        parent_tool_call_id="tool-parent-1",
        worker_agent=worker_agent,
        worker_timeout_seconds=1.0,
        result_max_chars=200,
    )

    result = await executor.execute(DelegatedTaskInput(objective="Research option A"))

    assert result["status"] == DELEGATION_STATUS_COMPLETED
    worker_result = result["result"]
    assert isinstance(worker_result, dict)
    assert worker_result["status"] == "completed"
    assert len(worker_agent.calls) == 1

    first_payload = worker_agent.calls[0]["payload"]
    assert isinstance(first_payload, dict)
    assert first_payload["user_id"] == "user-1"
    assert first_payload["organization_id"] == "org-1"
    assert first_payload["runtime_model"] == "gpt-5.2"
    assert first_payload["runtime_reasoning"] == "medium"
    assert first_payload["enabled_skill_ids"] == [
        "web-research",
        "workspace-analytics",
    ]
    assert first_payload["subagent_enabled"] is False
    assert first_payload["orchestration_mode"] == WORKER_ORCHESTRATION_MODE
    assert first_payload["delegation_depth"] == 1
    assert first_payload["delegation_parent_run_id"] == "tool-parent-1"
    assert first_payload["loaded_skills"] == []
    assert first_payload["todos_revision"] == 0
    assert len(first_payload["messages"]) == 1
    assert "Parent request" not in str(first_payload["messages"][0]["content"])


@pytest.mark.asyncio
async def test_delegation_executor_captures_worker_failure() -> None:
    worker_agent = _FakeWorkerAgent()
    executor = LeadAgentDelegationExecutor(
        parent_state=_parent_state(),
        parent_tool_call_id="tool-parent-2",
        worker_agent=worker_agent,
        worker_timeout_seconds=1.0,
        result_max_chars=200,
    )

    result = await executor.execute(
        DelegatedTaskInput(objective="FAIL_WORKER delegated task")
    )

    assert result["status"] == DELEGATION_STATUS_FAILED
    failed_result = result["result"]
    assert failed_result["status"] == WORKER_STATUS_FAILED
    assert failed_result["error"] == "worker exploded"


@pytest.mark.asyncio
async def test_delegation_executor_rejects_recursive_worker_delegation() -> None:
    worker_agent = _FakeWorkerAgent()
    executor = LeadAgentDelegationExecutor(
        parent_state=_parent_state(delegation_depth=1),
        parent_tool_call_id="tool-parent-3",
        worker_agent=worker_agent,
    )

    result = await executor.execute(DelegatedTaskInput(objective="Should be rejected"))

    assert result["status"] == DELEGATION_STATUS_REJECTED
    assert result["result"] is None
    assert worker_agent.calls == []
