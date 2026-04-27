from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command
from langgraph.prebuilt.tool_node import ToolCallRequest

from app.agents.middleware.tool_output_limit import (
    FETCH_CONTENT_MAX_ESTIMATED_TOKENS,
    ToolOutputLimitMiddleware,
    _count_tokens,
)
from app.agents.implementations.stock_research_agent.middleware import (
    StockResearchToolErrorMiddleware,
)


@tool
def fetch_content(url: str) -> str:
    """Fetch web page content."""


@tool
def search(query: str) -> str:
    """Search the web."""


@pytest.mark.asyncio
async def test_fetch_content_output_is_hard_capped_at_3000_estimated_tokens() -> None:
    middleware = ToolOutputLimitMiddleware()
    request = ToolCallRequest(
        tool_call={"id": "call-1", "name": "fetch_content", "args": {}},
        tool=fetch_content,
        state={},
        runtime=None,
    )
    oversized_content = "token " * (FETCH_CONTENT_MAX_ESTIMATED_TOKENS + 1000)

    async def _handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content=oversized_content, tool_call_id="call-1")

    response = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(response.content, str)
    truncated_token_count = _count_tokens(response.content)
    assert truncated_token_count is not None
    assert truncated_token_count <= FETCH_CONTENT_MAX_ESTIMATED_TOKENS
    assert response.content.startswith("token")
    assert "[TRUNCATED]" in response.content
    assert (
        f"Original estimated tokens: {_count_tokens(oversized_content)}."
        in response.content
    )


@pytest.mark.asyncio
async def test_fetch_content_output_under_limit_is_preserved() -> None:
    middleware = ToolOutputLimitMiddleware()
    request = ToolCallRequest(
        tool_call={"id": "call-1", "name": "fetch_content", "args": {}},
        tool=fetch_content,
        state={},
        runtime=None,
    )

    async def _handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="short content", tool_call_id="call-1")

    response = await middleware.awrap_tool_call(request, _handler)

    assert response.content == "short content"


@pytest.mark.asyncio
async def test_fetch_content_list_output_is_hard_capped() -> None:
    middleware = ToolOutputLimitMiddleware()
    request = ToolCallRequest(
        tool_call={"id": "call-1", "name": "fetch_content", "args": {}},
        tool=fetch_content,
        state={},
        runtime=None,
    )
    oversized_text = "token " * (FETCH_CONTENT_MAX_ESTIMATED_TOKENS + 1000)

    async def _handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content=[{"type": "text", "text": oversized_text}],
            tool_call_id="call-1",
        )

    response = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(response.content, str)
    truncated_token_count = _count_tokens(response.content)
    assert truncated_token_count is not None
    assert truncated_token_count <= FETCH_CONTENT_MAX_ESTIMATED_TOKENS
    assert response.content.startswith("token")
    assert "[TRUNCATED]" in response.content


@pytest.mark.asyncio
async def test_output_limit_middleware_does_not_truncate_search_results() -> None:
    middleware = ToolOutputLimitMiddleware()
    request = ToolCallRequest(
        tool_call={"id": "call-1", "name": "search", "args": {}},
        tool=search,
        state={},
        runtime=None,
    )
    oversized_content = "token " * (FETCH_CONTENT_MAX_ESTIMATED_TOKENS + 1000)

    async def _handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content=oversized_content, tool_call_id="call-1")

    response = await middleware.awrap_tool_call(request, _handler)

    assert response.content == oversized_content


@pytest.mark.asyncio
async def test_output_limit_middleware_preserves_command_results() -> None:
    middleware = ToolOutputLimitMiddleware()
    command = Command(update={"messages": []})
    request = ToolCallRequest(
        tool_call={"id": "call-1", "name": "fetch_content", "args": {}},
        tool=fetch_content,
        state={},
        runtime=None,
    )

    async def _handler(_: ToolCallRequest) -> Command:
        return command

    response = await middleware.awrap_tool_call(request, _handler)

    assert response is command


@pytest.mark.asyncio
async def test_output_limit_middleware_uses_tool_call_name_when_tool_is_missing() -> None:
    middleware = ToolOutputLimitMiddleware()
    request = ToolCallRequest(
        tool_call={"id": "call-1", "name": "fetch_content", "args": {}},
        tool=None,
        state={},
        runtime=None,
    )
    oversized_content = "token " * (FETCH_CONTENT_MAX_ESTIMATED_TOKENS + 1000)

    async def _handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content=oversized_content, tool_call_id="call-1")

    response = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(response.content, str)
    truncated_token_count = _count_tokens(response.content)
    assert truncated_token_count is not None
    assert truncated_token_count <= FETCH_CONTENT_MAX_ESTIMATED_TOKENS


def test_create_stock_research_agent_registers_output_limit_middleware(
    monkeypatch,
) -> None:
    from app.agents.implementations.stock_research_agent import agent as agent_module

    captured: dict[str, object] = {}
    fake_model = object()
    fake_tools = (search, fetch_content)

    monkeypatch.setattr(
        agent_module,
        "build_stock_research_model",
        lambda runtime_config=None: fake_model,
    )
    monkeypatch.setattr(
        agent_module,
        "get_stock_research_tool_surface",
        lambda: SimpleNamespace(tools=fake_tools),
    )
    monkeypatch.setattr(
        agent_module,
        "create_agent",
        lambda **kwargs: captured.update(kwargs) or "compiled-agent",
    )

    compiled_agent = agent_module.create_stock_research_agent()

    assert compiled_agent == "compiled-agent"
    assert captured["model"] is fake_model
    assert captured["tools"] == list(fake_tools)
    assert isinstance(captured["middleware"], list)
    assert isinstance(captured["middleware"][0], ToolOutputLimitMiddleware)
    assert isinstance(captured["middleware"][1], StockResearchToolErrorMiddleware)
