"""Todo middleware for the lead-agent runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any

from langchain.agents.middleware import ModelRequest, ModelResponse, TodoListMiddleware
from langchain.agents.middleware.todo import Todo
from langchain.tools import InjectedState, InjectedToolCallId
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from app.agents.implementations.lead_agent.middleware.constants import (
    LEAD_AGENT_TODO_REVISION_MARKER_PREFIX,
    LEAD_AGENT_TODO_STATE_MAX_ITEMS,
    TODO_STATUSES,
)
from app.agents.implementations.lead_agent.middleware.shared import (
    as_state_dict,
    merge_system_prompt,
    normalize_non_negative_int,
)
from app.agents.implementations.lead_agent.state import LeadAgentState
from app.prompts.system.lead_agent import (
    get_lead_agent_todo_system_prompt,
    get_lead_agent_todo_tool_description,
)


class LeadAgentTodoMiddleware(TodoListMiddleware):
    """Todo middleware with revision-aware prompt injection for compacted context."""

    state_schema = LeadAgentState

    def __init__(
        self,
        *,
        system_prompt: str | None = None,
        tool_description: str | None = None,
    ) -> None:
        super().__init__(
            system_prompt=system_prompt or get_lead_agent_todo_system_prompt(),
            tool_description=tool_description or get_lead_agent_todo_tool_description(),
        )

        @tool(description=self.tool_description)
        def write_todos(
            todos: list[Todo],
            tool_call_id: Annotated[str, InjectedToolCallId],
            current_revision: Annotated[
                int | None, InjectedState("todos_revision")
            ] = None,
        ) -> Command[Any]:
            """Create and manage the checkpoint-backed task list for this thread."""
            next_revision = normalize_non_negative_int(current_revision) + 1
            return Command(
                update={
                    "todos": todos,
                    "todos_revision": next_revision,
                    "messages": [
                        _build_todo_tool_message(
                            todos=todos,
                            tool_call_id=tool_call_id,
                            revision=next_revision,
                        )
                    ],
                }
            )

        self.tools = [write_todos]

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler,
    ) -> ModelResponse[Any]:
        state = as_state_dict(request.state)

        async def _handler(updated_request: ModelRequest[None]) -> ModelResponse[Any]:
            todo_prompt = _resolve_todo_state_prompt(state)
            if todo_prompt is None:
                return await handler(updated_request)

            prompt_with_todos = updated_request.override(
                system_message=SystemMessage(
                    content=merge_system_prompt(
                        updated_request.system_prompt,
                        [todo_prompt],
                    )
                )
            )
            return await handler(prompt_with_todos)

        return await super().awrap_model_call(request, _handler)


def _build_todo_tool_message(
    *,
    todos: list[Todo],
    tool_call_id: str,
    revision: int,
) -> ToolMessage:
    """Create one revision-tagged todo tool message for the current plan snapshot."""
    return ToolMessage(
        content=(
            f"Updated todo list to {todos}\n"
            f"{LEAD_AGENT_TODO_REVISION_MARKER_PREFIX}{revision}]"
        ),
        tool_call_id=tool_call_id,
        additional_kwargs={
            "lc_source": "write_todos",
            "todos_revision": revision,
        },
    )


def _resolve_todo_state_prompt(state: dict[str, Any]) -> str | None:
    """Return the todo snapshot prompt only when the current revision is not visible."""
    todos = state.get("todos")
    normalized_todos = _normalize_todos(todos)
    if not normalized_todos:
        return None

    messages = state.get("messages", [])
    current_revision = normalize_non_negative_int(state.get("todos_revision"))
    if _todo_state_is_visible(messages, current_revision):
        return None

    return _render_todo_state_prompt(normalized_todos)


def _render_todo_state_prompt(todos: Any) -> str | None:
    """Render the persisted todo snapshot into a bounded prompt section."""
    normalized_todos = _normalize_todos(todos)
    if not normalized_todos:
        return None

    total_count = len(normalized_todos)
    status_counts = {
        status: sum(1 for todo in normalized_todos if todo["status"] == status)
        for status in TODO_STATUSES
    }
    rendered_todos = normalized_todos[:LEAD_AGENT_TODO_STATE_MAX_ITEMS]
    remaining_count = total_count - len(rendered_todos)

    lines = [
        "<Todo_state>",
        "Current checkpoint-backed todo state for this thread.",
        "Treat this snapshot as the authoritative planning context for the current turn.",
        "",
        "Summary:",
        f"- total: {total_count}",
        f"- completed: {status_counts['completed']}",
        f"- in_progress: {status_counts['in_progress']}",
        f"- pending: {status_counts['pending']}",
        "",
        "Todos:",
    ]
    lines.extend(f"- [{todo['status']}] {todo['content']}" for todo in rendered_todos)
    if remaining_count > 0:
        lines.append(
            f"- ... {remaining_count} additional todo(s) omitted from prompt to keep context bounded"
        )
    lines.extend(
        [
            "",
            "Rules:",
            "- Prefer this todo snapshot over older transcript references or tool-message echoes.",
            "- Do not redo completed tasks unless the user explicitly asks to revisit them.",
            "- If the plan changes, update it with `write_todos` instead of relying on free-text notes.",
            "</Todo_state>",
        ]
    )
    return "\n".join(lines)


def _todo_state_is_visible(messages: Any, current_revision: int) -> bool:
    """Return whether the current todo revision is still visible in the context window."""
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        return False

    for message in reversed(messages):
        if not _is_todo_tool_message(message):
            continue
        revision = _extract_todo_revision(message)
        if current_revision > 0:
            if revision == current_revision:
                return True
            continue
        return True
    return False


def _normalize_todos(value: Any) -> list[dict[str, str]]:
    """Normalize the checkpoint-backed todo snapshot into prompt-safe entries."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []

    normalized_todos: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        status = str(item.get("status", "")).strip()
        if not content or status not in TODO_STATUSES:
            continue
        normalized_todos.append({"content": content, "status": status})
    return normalized_todos


def _is_todo_tool_message(message: Any) -> bool:
    """Return whether the message is a revision-tagged or legacy write_todos tool echo."""
    if not isinstance(message, ToolMessage):
        return False
    content = str(message.content)
    if str(message.additional_kwargs.get("lc_source")) == "write_todos":
        return True
    return content.startswith("Updated todo list to")


def _extract_todo_revision(message: ToolMessage) -> int | None:
    """Extract one todo revision marker from a persisted tool message."""
    additional_revision = message.additional_kwargs.get("todos_revision")
    if isinstance(additional_revision, int):
        return additional_revision

    content = str(message.content)
    marker_index = content.find(LEAD_AGENT_TODO_REVISION_MARKER_PREFIX)
    if marker_index < 0:
        return None

    start_index = marker_index + len(LEAD_AGENT_TODO_REVISION_MARKER_PREFIX)
    end_index = content.find("]", start_index)
    if end_index < 0:
        return None
    try:
        return int(content[start_index:end_index])
    except ValueError:
        return None
