from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import (
    ModelRequest,
    ModelResponse,
    SummarizationMiddleware,
)
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import ToolException, tool
from langgraph.prebuilt.tool_node import ToolCallRequest

from app.agents.middleware.tool_output_limit import ToolOutputLimitMiddleware
from app.agents.implementations.stock_agent.middleware.builder import (
    build_stock_agent_middleware,
)
from app.agents.implementations.stock_agent.middleware.constants import (
    STOCK_AGENT_SUMMARIZATION_FRACTION_TRIGGER,
    STOCK_AGENT_SUMMARIZATION_KEEP,
    STOCK_AGENT_SUMMARIZATION_MESSAGE_TRIGGER,
    STOCK_AGENT_SUMMARIZATION_TOKEN_TRIGGER,
    STOCK_AGENT_SUMMARIZATION_TRIM_TOKENS,
)
from app.agents.implementations.stock_agent.middleware.delegation_limit import (
    StockAgentDelegationLimitMiddleware,
)
from app.agents.implementations.stock_agent.middleware.orchestration import (
    StockAgentOrchestrationPromptMiddleware,
)
from app.agents.implementations.stock_agent.middleware.skill_prompt import (
    StockAgentSkillPromptMiddleware,
)
from app.agents.implementations.stock_agent.middleware.todo import (
    StockAgentTodoMiddleware,
)
from app.agents.implementations.stock_agent.middleware.tool_error import (
    StockAgentToolErrorMiddleware,
)
from app.agents.implementations.stock_agent.middleware.tool_selection import (
    StockAgentToolSelectionMiddleware,
)
from app.agents.implementations.stock_agent.state import StockAgentState
from app.agents.implementations.stock_agent.tools import load_skill
from app.prompts.system.stock_agent import (
    get_stock_agent_orchestration_system_prompt,
    get_stock_agent_summarization_prompt,
    get_stock_agent_system_prompt,
    get_stock_agent_todo_system_prompt,
    get_stock_agent_todo_tool_description,
    get_stock_agent_worker_system_prompt,
)


def _skill(
    *,
    skill_id: str,
    description: str,
    activation_prompt: str,
    version: str = "1.0.0",
) -> SimpleNamespace:
    return SimpleNamespace(
        _id=f"{skill_id}-id",
        skill_id=skill_id,
        name=skill_id.replace("-", " ").title(),
        description=description,
        activation_prompt=activation_prompt,
        allowed_tool_names=["search_docs"],
        version=version,
        created_by="user-1",
        organization_id="org-1",
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


def _build_runtime_middleware(
    *,
    profile: dict[str, object] | None = None,
) -> list[object]:
    return build_stock_agent_middleware(
        SimpleNamespace(_llm_type="test-chat-model", profile=profile)
    )


def test_stock_agent_system_prompt_defines_vietnam_stock_context_gate() -> None:
    prompt = get_stock_agent_system_prompt()

    assert "You only support Vietnam-listed equities on HOSE, HNX, and UPCoM" in prompt
    assert "Stock Context Gate" in prompt
    assert 'for example "analyze FPT"' in prompt
    assert "The user requests technical analysis and does not provide a timeframe" in prompt
    assert "Do not default the timeframe" in prompt
    assert "Write the stance label in the same language as the user" in prompt
    assert "`Tích lũy`, `Theo dõi`, `Thận trọng`, or `Giảm tỷ trọng`" in prompt
    assert "`Accumulate`, `Watch`, `Cautious`, or `Reduce Exposure`" in prompt
    assert 'Do not add a generic "not financial advice" disclaimer' in prompt


def _todo_middleware() -> StockAgentTodoMiddleware:
    middleware = next(
        item
        for item in _build_runtime_middleware()
        if isinstance(item, StockAgentTodoMiddleware)
    )
    return middleware


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


@tool
def delegate_tasks(tasks: str) -> str:
    """Delegate work to isolated worker agents."""


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
    middleware = StockAgentSkillPromptMiddleware(skill_access_resolver=resolver)
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
    middleware = StockAgentSkillPromptMiddleware(skill_access_resolver=resolver)
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
async def test_orchestration_prompt_middleware_injects_manager_guidance_for_subagent_turns() -> None:
    middleware = StockAgentOrchestrationPromptMiddleware()
    request = _request(
        state={
            "messages": [],
            "subagent_enabled": True,
            "delegation_depth": 0,
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
    assert get_stock_agent_orchestration_system_prompt() in updated_request.system_prompt


@pytest.mark.asyncio
async def test_orchestration_prompt_middleware_preserves_subagent_ready_base_prompt() -> None:
    middleware = StockAgentOrchestrationPromptMiddleware()
    request = _request(
        state={
            "messages": [],
            "subagent_enabled": True,
            "delegation_depth": 0,
        },
        system_prompt=get_stock_agent_system_prompt(subagent_enabled=True),
    )
    captured: dict[str, ModelRequest[None]] = {}

    async def _handler(updated_request: ModelRequest[None]) -> ModelResponse[object]:
        captured["request"] = updated_request
        return ModelResponse(result=[AIMessage(content="ok")])

    await middleware.awrap_model_call(request, _handler)

    updated_request = captured["request"]
    assert updated_request.system_prompt is not None
    assert (
        "DECOMPOSITION CHECK: Can this task be broken into 2+ parallel sub-tasks?"
        in updated_request.system_prompt
    )
    assert "Orchestrator Mode" in updated_request.system_prompt
    assert get_stock_agent_orchestration_system_prompt() in updated_request.system_prompt


@pytest.mark.asyncio
async def test_orchestration_prompt_middleware_injects_worker_guidance_for_worker_runs() -> None:
    middleware = StockAgentOrchestrationPromptMiddleware()
    request = _request(
        state={
            "messages": [],
            "subagent_enabled": True,
            "delegation_depth": 1,
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
    assert updated_request.system_prompt == get_stock_agent_worker_system_prompt()


@pytest.mark.asyncio
async def test_tool_selection_middleware_filters_to_base_skill_and_delegation_surface() -> None:
    middleware = StockAgentToolSelectionMiddleware()
    handler_requests: list[ModelRequest[None]] = []
    todo_tool = _todo_middleware().tools[0]

    async def _handler(updated_request: ModelRequest[None]) -> ModelResponse[object]:
        handler_requests.append(updated_request)
        return ModelResponse(result=[AIMessage(content="ok")])

    pre_activation_request = _request(
        state={
            "messages": [],
        },
        tools=[
            load_skill,
            todo_tool,
            search,
            fetch_content,
            search_docs,
            delegate_tasks,
            secret_tool,
        ],
    )
    await middleware.awrap_model_call(pre_activation_request, _handler)

    orchestrated_parent_request = _request(
        state={
            "messages": [],
            "enabled_skill_ids": ["web-research"],
            "active_skill_id": "web-research",
            "allowed_tool_names": ["search_docs"],
            "subagent_enabled": True,
            "delegation_depth": 0,
        },
        tools=[
            load_skill,
            todo_tool,
            search,
            fetch_content,
            search_docs,
            delegate_tasks,
            secret_tool,
        ],
    )
    await middleware.awrap_model_call(orchestrated_parent_request, _handler)

    worker_request = _request(
        state={
            "messages": [],
            "enabled_skill_ids": ["web-research"],
            "active_skill_id": "web-research",
            "allowed_tool_names": ["search_docs"],
            "subagent_enabled": True,
            "delegation_depth": 1,
        },
        tools=[
            load_skill,
            todo_tool,
            search,
            fetch_content,
            search_docs,
            delegate_tasks,
            secret_tool,
        ],
    )
    await middleware.awrap_model_call(worker_request, _handler)

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
        "delegate_tasks",
    ]
    assert [tool.name for tool in handler_requests[2].tools] == [
        "load_skill",
        "write_todos",
        "search",
        "fetch_content",
        "search_docs",
    ]


@pytest.mark.asyncio
async def test_tool_error_middleware_converts_tool_exception_to_error_message() -> None:
    middleware = StockAgentToolErrorMiddleware()
    request = ToolCallRequest(
        tool_call={"id": "call-1", "name": "extract_content", "args": {}},
        tool=fetch_content,
        state={},
        runtime=None,
    )

    async def _handler(_: ToolCallRequest) -> ToolMessage:
        raise ToolException(
            "Error executing tool extract_content: Failed to fetch https://filum.ai/about-us: HTTP 404"
        )

    response = await middleware.awrap_tool_call(request, _handler)

    assert response.tool_call_id == "call-1"
    assert response.status == "error"
    assert "extract_content" in str(response.content)
    assert "HTTP 404" in str(response.content)


@pytest.mark.asyncio
async def test_delegation_limit_middleware_rejects_more_than_three_parallel_delegate_calls() -> None:
    middleware = StockAgentDelegationLimitMiddleware()
    result = await middleware.aafter_model(
        {
            "messages": [
                AIMessage(
                    content="Delegating work",
                    tool_calls=[
                        {"id": "call-1", "name": "delegate_tasks", "args": {"task": {"objective": "A"}}},
                        {"id": "call-2", "name": "delegate_tasks", "args": {"task": {"objective": "B"}}},
                        {"id": "call-3", "name": "delegate_tasks", "args": {"task": {"objective": "C"}}},
                        {"id": "call-4", "name": "delegate_tasks", "args": {"task": {"objective": "D"}}},
                    ],
                )
            ]
        },
        runtime=None,
    )

    assert result is not None
    messages = result["messages"]
    assert len(messages) == 4
    assert all(isinstance(message, ToolMessage) for message in messages)
    assert all(message.status == "error" for message in messages)
    assert all("maximum allowed per model invocation is 3" in str(message.content) for message in messages)


@pytest.mark.asyncio
async def test_todo_middleware_injects_checkpoint_backed_todos_when_current_revision_is_not_visible() -> None:
    middleware = _todo_middleware()
    request = _request(
        state={
            "messages": [
                ToolMessage(
                    content="Updated todo list to [{'content': 'stale todo', 'status': 'pending'}]",
                    tool_call_id="tool-1",
                )
            ],
            "todos": [
                {"content": "Inspect current runtime state", "status": "completed"},
                {"content": "Inject authoritative todo snapshot", "status": "in_progress"},
                {"content": "Verify prompt continuity after compaction", "status": "pending"},
            ],
            "todos_revision": 2,
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
    assert "<Todo_state>" in updated_request.system_prompt
    assert "Current checkpoint-backed todo state for this thread." in updated_request.system_prompt
    assert "- total: 3" in updated_request.system_prompt
    assert "- completed: 1" in updated_request.system_prompt
    assert "- in_progress: 1" in updated_request.system_prompt
    assert "- pending: 1" in updated_request.system_prompt
    assert "[completed] Inspect current runtime state" in updated_request.system_prompt
    assert "[in_progress] Inject authoritative todo snapshot" in updated_request.system_prompt
    assert "[pending] Verify prompt continuity after compaction" in updated_request.system_prompt
    assert "stale todo" not in updated_request.system_prompt
    assert "Prefer this todo snapshot over older transcript references" in updated_request.system_prompt


@pytest.mark.asyncio
async def test_todo_middleware_skips_prompt_injection_when_current_revision_is_still_visible() -> None:
    middleware = _todo_middleware()
    request = _request(
        state={
            "messages": [
                ToolMessage(
                    content=(
                        "Updated todo list to [{'content': 'Track prompt visibility', 'status': 'in_progress'}]\n"
                        "[todos_revision=3]"
                    ),
                    tool_call_id="tool-1",
                    additional_kwargs={
                        "lc_source": "write_todos",
                        "todos_revision": 3,
                    },
                )
            ],
            "todos": [
                {"content": "Track prompt visibility", "status": "in_progress"},
            ],
            "todos_revision": 3,
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
    assert "write_todos" in updated_request.system_prompt
    assert "<Todo_state>" not in updated_request.system_prompt


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
    skill_prompt = StockAgentSkillPromptMiddleware(skill_access_resolver=resolver)
    orchestration_prompt = StockAgentOrchestrationPromptMiddleware()
    todo_middleware = _todo_middleware()
    tool_selection = StockAgentToolSelectionMiddleware()
    request = _request(
        state={
            "messages": [],
            "user_id": "user-1",
            "organization_id": "org-1",
            "enabled_skill_ids": ["web-research"],
            "active_skill_id": "web-research",
            "loaded_skills": ["web-research"],
            "allowed_tool_names": ["search_docs"],
            "subagent_enabled": True,
            "delegation_depth": 0,
            "todos": [
                {
                    "content": "Design prompt-visible todo state injection",
                    "status": "in_progress",
                },
                {
                    "content": "Validate middleware ordering",
                    "status": "pending",
                },
            ],
            "todos_revision": 4,
        },
        system_prompt="Base system prompt.",
        tools=[
            load_skill,
            todo_middleware.tools[0],
            search,
            fetch_content,
            search_docs,
            delegate_tasks,
            secret_tool,
        ],
    )

    final_request = await _run_middleware_chain(
        request,
        [
            skill_prompt,
            orchestration_prompt,
            todo_middleware,
            tool_selection,
        ],
    )

    assert final_request.system_prompt is not None
    assert "Base system prompt." in final_request.system_prompt
    assert "<Available Skills>" in final_request.system_prompt
    assert "Active skill: web-research (version 2.1.0)" in final_request.system_prompt
    assert get_stock_agent_orchestration_system_prompt() in final_request.system_prompt
    assert "write_todos" in final_request.system_prompt
    assert "simple tasks (< 3 steps)" in final_request.system_prompt
    assert "<Todo_state>" in final_request.system_prompt
    assert "[in_progress] Design prompt-visible todo state injection" in final_request.system_prompt
    assert "[pending] Validate middleware ordering" in final_request.system_prompt
    assert [tool.name for tool in final_request.tools] == [
        "load_skill",
        "write_todos",
        "search",
        "fetch_content",
        "search_docs",
        "delegate_tasks",
    ]


@pytest.mark.asyncio
async def test_simple_turn_can_finish_without_todo_creation_while_complex_turn_keeps_planning_tool() -> None:
    todo_middleware = _todo_middleware()
    tool_selection = StockAgentToolSelectionMiddleware()

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


def test_stock_agent_runtime_registers_todo_middleware_with_complex_task_guidance() -> None:
    middlewares = _build_runtime_middleware(profile={"max_input_tokens": 100000})
    assert len(middlewares) == 8
    assert isinstance(middlewares[0], SummarizationMiddleware)
    assert isinstance(middlewares[1], StockAgentOrchestrationPromptMiddleware)
    assert isinstance(middlewares[2], StockAgentSkillPromptMiddleware)
    assert isinstance(middlewares[3], StockAgentTodoMiddleware)
    assert isinstance(middlewares[4], StockAgentDelegationLimitMiddleware)
    assert isinstance(middlewares[5], StockAgentToolSelectionMiddleware)
    assert isinstance(middlewares[6], ToolOutputLimitMiddleware)
    assert isinstance(middlewares[7], StockAgentToolErrorMiddleware)

    summarization_middleware = middlewares[0]
    assert summarization_middleware.trigger == [
        STOCK_AGENT_SUMMARIZATION_FRACTION_TRIGGER,
        STOCK_AGENT_SUMMARIZATION_MESSAGE_TRIGGER,
        STOCK_AGENT_SUMMARIZATION_TOKEN_TRIGGER,
    ]
    assert summarization_middleware.keep == STOCK_AGENT_SUMMARIZATION_KEEP
    assert (
        summarization_middleware.trim_tokens_to_summarize
        == STOCK_AGENT_SUMMARIZATION_TRIM_TOKENS
    )
    assert (
        summarization_middleware.summary_prompt
        == get_stock_agent_summarization_prompt()
    )
    assert "## SESSION INTENT" in summarization_middleware.summary_prompt
    assert "## KEY DECISIONS" in summarization_middleware.summary_prompt
    assert "## CONSTRAINTS" in summarization_middleware.summary_prompt
    assert "## NEXT STEPS" in summarization_middleware.summary_prompt

    todo_middleware = middlewares[3]
    todo_system_prompt = get_stock_agent_todo_system_prompt()
    todo_tool_description = get_stock_agent_todo_tool_description()
    assert todo_middleware.system_prompt == todo_system_prompt
    assert todo_middleware.tool_description == todo_tool_description
    assert "complex" in todo_system_prompt.lower()
    assert "simple" in todo_system_prompt.lower()
    assert "structured task list" in todo_tool_description.lower()


def test_stock_agent_runtime_skips_fraction_trigger_when_model_profile_is_unavailable() -> None:
    middlewares = _build_runtime_middleware()
    summarization_middleware = middlewares[0]

    assert isinstance(summarization_middleware, SummarizationMiddleware)
    assert summarization_middleware.trigger == [
        STOCK_AGENT_SUMMARIZATION_MESSAGE_TRIGGER,
        STOCK_AGENT_SUMMARIZATION_TOKEN_TRIGGER,
    ]


def test_stock_agent_state_keeps_todos_in_middleware_backed_runtime_state() -> None:
    assert "todos" not in StockAgentState.__annotations__
    assert "todos_revision" in StockAgentState.__annotations__
