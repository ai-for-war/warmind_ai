from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import (
    ModelRequest,
    ModelResponse,
    TodoListMiddleware,
)
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.agents.implementations.lead_agent.middleware import (
    LEAD_AGENT_MIDDLEWARE,
    LeadAgentSkillPromptMiddleware,
    LeadAgentToolSelectionMiddleware,
)
from app.agents.implementations.lead_agent.state import LeadAgentState
from app.agents.implementations.lead_agent.tools import load_skill
from app.domain.models.lead_agent_skill import LeadAgentSkill
from app.prompts.system.lead_agent import (
    get_lead_agent_todo_system_prompt,
    get_lead_agent_todo_tool_description,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _skill(
    *,
    skill_id: str,
    description: str,
    activation_prompt: str,
    version: str = "1.0.0",
) -> LeadAgentSkill:
    return LeadAgentSkill(
        _id=f"{skill_id}-id",
        skill_id=skill_id,
        name=skill_id.replace("-", " ").title(),
        description=description,
        activation_prompt=activation_prompt,
        allowed_tool_names=["search_docs"],
        version=version,
        created_by="user-1",
        organization_id="org-1",
        created_at=_now(),
        updated_at=_now(),
    )


def _request(
    *,
    state: dict[str, object],
    tools: list[object] | None = None,
    system_prompt: str | None = None,
) -> ModelRequest[None]:
    return ModelRequest(
        model=object(),
        messages=[],
        system_prompt=system_prompt,
        tools=tools or [],
        state=state,
        runtime=None,
    )


async def _run_middleware_chain(
    request: ModelRequest[None],
    middlewares: list[object],
) -> ModelRequest[None]:
    captured: dict[str, ModelRequest[None]] = {}

    async def _terminal_handler(
        final_request: ModelRequest[None],
    ) -> ModelResponse[object]:
        captured["request"] = final_request
        return ModelResponse(result=[AIMessage(content="ok")])

    handler = _terminal_handler
    for middleware in reversed(middlewares):
        next_handler = handler

        async def _wrapped_handler(
            updated_request: ModelRequest[None],
            *,
            _middleware=middleware,
            _next_handler=next_handler,
        ) -> ModelResponse[object]:
            return await _middleware.awrap_model_call(updated_request, _next_handler)

        handler = _wrapped_handler

    await handler(request)
    return captured["request"]


@tool
def search_docs(query: str) -> str:
    """Search docs."""


@tool
def search(query: str) -> str:
    """Search the web."""


@tool
def fetch_content(url: str) -> str:
    """Fetch web page content."""


@tool
def secret_tool(query: str) -> str:
    """Secret tool."""


@pytest.mark.asyncio
async def test_prompt_middleware_injects_lightweight_skill_summaries() -> None:
    resolver = SimpleNamespace(
        resolve_skill_definitions=AsyncMock(
            return_value=[
                _skill(
                    skill_id="web-research",
                    description="Research external sources.",
                    activation_prompt="Use external sources carefully.",
                ),
                _skill(
                    skill_id="workspace-analytics",
                    description="Analyze workspace metrics.",
                    activation_prompt="Prefer internal metrics.",
                ),
            ]
        )
    )
    middleware = LeadAgentSkillPromptMiddleware(skill_access_resolver=resolver)
    request = _request(
        state={
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
            "enabled_skill_ids": ["web-research", "workspace-analytics"],
        },
        system_prompt="Base system prompt.",
    )
    captured: dict[str, ModelRequest[None]] = {}

    async def _handler(updated_request: ModelRequest[None]) -> ModelResponse[object]:
        captured["request"] = updated_request
        return ModelResponse(result=[AIMessage(content="ok")])

    await middleware.awrap_model_call(request, _handler)

    updated_request = captured["request"]
    assert updated_request.system_prompt is not None
    assert "Base system prompt." in updated_request.system_prompt
    assert "<Available Skills>" in updated_request.system_prompt
    assert "skill_id: web-research" in updated_request.system_prompt
    assert "Research external sources." in updated_request.system_prompt
    assert "Activated instructions:" not in updated_request.system_prompt


@pytest.mark.asyncio
async def test_prompt_middleware_reinjects_active_skill_instructions() -> None:
    resolver = SimpleNamespace(
        resolve_skill_definitions=AsyncMock(
            return_value=[
                _skill(
                    skill_id="web-research",
                    description="Research external sources.",
                    activation_prompt="Use external sources carefully.",
                    version="2.1.0",
                )
            ]
        )
    )
    middleware = LeadAgentSkillPromptMiddleware(skill_access_resolver=resolver)
    request = _request(
        state={
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
            "enabled_skill_ids": ["web-research"],
            "active_skill_id": "web-research",
            "loaded_skills": ["web-research"],
        },
    )
    captured: dict[str, ModelRequest[None]] = {}

    async def _handler(updated_request: ModelRequest[None]) -> ModelResponse[object]:
        captured["request"] = updated_request
        return ModelResponse(result=[AIMessage(content="ok")])

    await middleware.awrap_model_call(request, _handler)

    updated_request = captured["request"]
    assert updated_request.system_prompt is not None
    assert "Active skill: web-research (version 2.1.0)" in updated_request.system_prompt
    assert "Use external sources carefully." in updated_request.system_prompt


@pytest.mark.asyncio
async def test_tool_selection_middleware_filters_to_base_or_skill_allowed_surface() -> None:
    middleware = LeadAgentToolSelectionMiddleware()
    handler_requests: list[ModelRequest[None]] = []
    todo_tool = LEAD_AGENT_MIDDLEWARE[1].tools[0]

    async def _handler(updated_request: ModelRequest[None]) -> ModelResponse[object]:
        handler_requests.append(updated_request)
        return ModelResponse(result=[AIMessage(content="ok")])

    pre_activation_request = _request(
        state={
            "messages": [],
        },
        tools=[load_skill, todo_tool, search, fetch_content, search_docs, secret_tool],
    )
    await middleware.awrap_model_call(pre_activation_request, _handler)

    active_skill_request = _request(
        state={
            "messages": [],
            "enabled_skill_ids": ["web-research"],
            "active_skill_id": "web-research",
            "allowed_tool_names": ["search_docs"],
        },
        tools=[load_skill, todo_tool, search, fetch_content, search_docs, secret_tool],
    )
    await middleware.awrap_model_call(active_skill_request, _handler)

    assert [tool.name for tool in handler_requests[0].tools] == [
        "load_skill",
        "write_todos",
        "search",
        "fetch_content",
    ]
    assert [tool.name for tool in handler_requests[1].tools] == [
        "load_skill",
        "write_todos",
        "search",
        "fetch_content",
        "search_docs",
    ]


@pytest.mark.asyncio
async def test_middleware_chain_preserves_skill_prompt_todo_guidance_and_filtered_tools() -> None:
    resolver = SimpleNamespace(
        resolve_skill_definitions=AsyncMock(
            return_value=[
                _skill(
                    skill_id="web-research",
                    description="Research external sources.",
                    activation_prompt="Use external sources carefully.",
                    version="2.1.0",
                )
            ]
        )
    )
    skill_prompt = LeadAgentSkillPromptMiddleware(skill_access_resolver=resolver)
    todo_middleware = LEAD_AGENT_MIDDLEWARE[1]
    tool_selection = LeadAgentToolSelectionMiddleware()
    request = _request(
        state={
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
            "enabled_skill_ids": ["web-research"],
            "active_skill_id": "web-research",
            "loaded_skills": ["web-research"],
            "allowed_tool_names": ["search_docs"],
        },
        system_prompt="Base system prompt.",
        tools=[
            load_skill,
            todo_middleware.tools[0],
            search,
            fetch_content,
            search_docs,
            secret_tool,
        ],
    )

    final_request = await _run_middleware_chain(
        request,
        [skill_prompt, todo_middleware, tool_selection],
    )

    assert final_request.system_prompt is not None
    assert "Base system prompt." in final_request.system_prompt
    assert "<Available Skills>" in final_request.system_prompt
    assert "Active skill: web-research (version 2.1.0)" in final_request.system_prompt
    assert "write_todos" in final_request.system_prompt
    assert "simple tasks (< 3 steps)" in final_request.system_prompt
    assert [tool.name for tool in final_request.tools] == [
        "load_skill",
        "write_todos",
        "search",
        "fetch_content",
        "search_docs",
    ]


@pytest.mark.asyncio
async def test_simple_turn_can_finish_without_todo_creation_while_complex_turn_keeps_planning_tool() -> None:
    todo_middleware = LEAD_AGENT_MIDDLEWARE[1]
    tool_selection = LeadAgentToolSelectionMiddleware()

    simple_turn_result = await todo_middleware.aafter_model(
        {"messages": [AIMessage(content="Handled directly without todos.")]},
        runtime=None,
    )
    assert simple_turn_result is None

    complex_request = _request(
        state={
            "messages": [],
            "enabled_skill_ids": ["web-research"],
            "active_skill_id": "web-research",
            "allowed_tool_names": ["search_docs"],
        },
        tools=[
            load_skill,
            todo_middleware.tools[0],
            search,
            fetch_content,
            search_docs,
        ],
    )
    filtered_request = await _run_middleware_chain(
        complex_request,
        [tool_selection],
    )

    assert "write_todos" in [tool.name for tool in filtered_request.tools]


def test_lead_agent_runtime_registers_todo_middleware_with_complex_task_guidance() -> None:
    assert len(LEAD_AGENT_MIDDLEWARE) == 3
    assert isinstance(LEAD_AGENT_MIDDLEWARE[0], LeadAgentSkillPromptMiddleware)
    assert isinstance(LEAD_AGENT_MIDDLEWARE[1], TodoListMiddleware)
    assert isinstance(LEAD_AGENT_MIDDLEWARE[2], LeadAgentToolSelectionMiddleware)

    todo_middleware = LEAD_AGENT_MIDDLEWARE[1]
    todo_system_prompt = get_lead_agent_todo_system_prompt()
    todo_tool_description = get_lead_agent_todo_tool_description()
    assert todo_middleware.system_prompt == todo_system_prompt
    assert todo_middleware.tool_description == todo_tool_description
    assert "complex" in todo_system_prompt.lower()
    assert "simple" in todo_system_prompt.lower()
    assert "structured task list" in todo_tool_description.lower()


def test_lead_agent_state_keeps_todos_in_middleware_backed_runtime_state() -> None:
    assert "todos" not in LeadAgentState.__annotations__
