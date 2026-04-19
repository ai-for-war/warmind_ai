"""Lead-agent middleware for skill-aware prompt injection and tool exposure."""

from __future__ import annotations

from typing import Annotated
from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    SummarizationMiddleware,
    TodoListMiddleware,
    ToolCallRequest,
)
from langchain.agents.middleware.todo import Todo
from langchain.chat_models import BaseChatModel
from langchain.tools import InjectedState, InjectedToolCallId
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.types import Command

from app.agents.implementations.lead_agent.state import LeadAgentState
from app.config.settings import get_settings
from app.infrastructure.mcp.research_tools import RESEARCH_TOOL_NAMES
from app.prompts.system.lead_agent import (
    get_lead_agent_orchestration_system_prompt,
    get_lead_agent_summarization_prompt,
    get_lead_agent_todo_system_prompt,
    get_lead_agent_todo_tool_description,
    get_lead_agent_worker_system_prompt,
)
from app.services.ai.lead_agent_skill_access_resolver import (
    LeadAgentSkillAccessResolver,
)

_BASE_SKILL_TOOL_NAMES = {"load_skill", "write_todos", *RESEARCH_TOOL_NAMES}
_DELEGATION_TOOL_NAME = "delegate_tasks"
LEAD_AGENT_SUMMARIZATION_MESSAGE_TRIGGER = ("messages", 40)
LEAD_AGENT_SUMMARIZATION_TOKEN_TRIGGER = ("tokens", 80000)
LEAD_AGENT_SUMMARIZATION_FRACTION_TRIGGER = ("fraction", 0.8)
LEAD_AGENT_SUMMARIZATION_KEEP = ("messages", 12)
LEAD_AGENT_SUMMARIZATION_TRIM_TOKENS = 6000
LEAD_AGENT_TODO_STATE_MAX_ITEMS = 20
LEAD_AGENT_TODO_REVISION_MARKER_PREFIX = "[todos_revision="
_TODO_STATUSES = ("pending", "in_progress", "completed")


class LeadAgentSkillPromptMiddleware(AgentMiddleware[LeadAgentState, None, Any]):
    """Inject skill discovery and activation prompts before each model call."""

    state_schema = LeadAgentState
    tools: Sequence[BaseTool] = ()

    def __init__(
        self,
        skill_access_resolver: LeadAgentSkillAccessResolver | None = None,
    ) -> None:
        self.skill_access_resolver = skill_access_resolver

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler,
    ) -> ModelResponse[Any]:
        state = _as_state_dict(request.state)
        user_id = _normalize_optional_string(state.get("user_id"))
        organization_id = _normalize_optional_string(state.get("organization_id"))
        enabled_skill_ids = _normalize_unique_strings(
            state.get("enabled_skill_ids", [])
        )
        if not user_id or not organization_id or not enabled_skill_ids:
            return await handler(request)

        resolver = self.skill_access_resolver or _get_lead_agent_skill_access_resolver()
        enabled_skills = await resolver.resolve_skill_definitions(
            user_id=user_id,
            organization_id=organization_id,
            skill_ids=enabled_skill_ids,
        )
        if not enabled_skills:
            return await handler(request)

        prompt_sections = [
            _render_enabled_skill_summaries(enabled_skills),
        ]
        active_skill_id = _normalize_optional_string(state.get("active_skill_id"))
        if active_skill_id:
            active_skill = next(
                (
                    skill
                    for skill in enabled_skills
                    if skill.skill_id == active_skill_id
                ),
                None,
            )
            if active_skill is not None:
                prompt_sections.append(_render_active_skill_prompt(active_skill))

        updated_request = request.override(
            system_message=SystemMessage(
                content=_merge_system_prompt(
                    request.system_prompt,
                    prompt_sections,
                )
            )
        )
        return await handler(updated_request)


class LeadAgentToolSelectionMiddleware(AgentMiddleware[LeadAgentState, None, Any]):
    """Filter visible tools to the base or active-skill subset for each call."""

    state_schema = LeadAgentState
    tools: Sequence[BaseTool] = ()

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler,
    ) -> ModelResponse[Any]:
        state = _as_state_dict(request.state)
        active_skill_id = _normalize_optional_string(state.get("active_skill_id"))
        allowed_tool_names = _normalize_unique_strings(
            state.get("allowed_tool_names", [])
        )
        subagent_enabled = _normalize_bool(state.get("subagent_enabled"))
        delegation_depth = _normalize_non_negative_int(state.get("delegation_depth"))

        visible_tool_names = _visible_tool_names(
            active_skill_id=active_skill_id,
            allowed_tool_names=allowed_tool_names,
            subagent_enabled=subagent_enabled,
            delegation_depth=delegation_depth,
        )
        filtered_tools = [
            tool for tool in request.tools if _tool_name(tool) in visible_tool_names
        ]
        return await handler(request.override(tools=filtered_tools))


class LeadAgentDelegationLimitMiddleware(AgentMiddleware[LeadAgentState, None, Any]):
    """Reject over-limit parallel delegation batches from a single model turn."""

    state_schema = LeadAgentState
    tools: Sequence[BaseTool] = ()

    def after_model(
        self,
        state: LeadAgentState,
        runtime,
    ) -> dict[str, Any] | None:
        """Return tool errors when one model turn exceeds the delegation fan-out limit."""
        messages = state["messages"]
        if not messages:
            return None

        last_ai_msg = next(
            (msg for msg in reversed(messages) if isinstance(msg, AIMessage)),
            None,
        )
        if not last_ai_msg or not last_ai_msg.tool_calls:
            return None

        delegate_calls = [
            tool_call
            for tool_call in last_ai_msg.tool_calls
            if tool_call["name"] == _DELEGATION_TOOL_NAME
        ]
        max_parallel_subagents = get_settings().LEAD_AGENT_MAX_PARALLEL_SUBAGENTS
        if len(delegate_calls) <= max_parallel_subagents:
            return None

        error_messages = [
            ToolMessage(
                content=(
                    f"Error: `{_DELEGATION_TOOL_NAME}` was called {len(delegate_calls)} times in "
                    f"parallel, but the maximum allowed per model invocation is "
                    f"{max_parallel_subagents}. Limit each turn to at most "
                    f"{max_parallel_subagents} delegated subagents."
                ),
                tool_call_id=str(tool_call["id"]),
                status="error",
            )
            for tool_call in delegate_calls
        ]
        return {"messages": error_messages}

    async def aafter_model(
        self,
        state: LeadAgentState,
        runtime,
    ) -> dict[str, Any] | None:
        """Async wrapper for the delegation batch limit guardrail."""
        return self.after_model(state, runtime)


class LeadAgentOrchestrationPromptMiddleware(
    AgentMiddleware[LeadAgentState, None, Any]
):
    """Inject orchestration or worker-specific behavior prompts per turn."""

    state_schema = LeadAgentState
    tools: Sequence[BaseTool] = ()

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler,
    ) -> ModelResponse[Any]:
        state = _as_state_dict(request.state)
        prompt_update = _resolve_orchestration_prompt_update(
            state,
            existing_prompt=request.system_prompt,
        )
        if prompt_update is None:
            return await handler(request)

        updated_request = request.override(
            system_message=SystemMessage(content=prompt_update)
        )
        return await handler(updated_request)


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
            next_revision = _normalize_non_negative_int(current_revision) + 1
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
        state = _as_state_dict(request.state)

        async def _handler(updated_request: ModelRequest[None]) -> ModelResponse[Any]:
            todo_prompt = _resolve_todo_state_prompt(state)
            if todo_prompt is None:
                return await handler(updated_request)

            prompt_with_todos = updated_request.override(
                system_message=SystemMessage(
                    content=_merge_system_prompt(
                        updated_request.system_prompt,
                        [todo_prompt],
                    )
                )
            )
            return await handler(prompt_with_todos)

        return await super().awrap_model_call(request, _handler)


class LeadAgentToolErrorMiddleware(AgentMiddleware[LeadAgentState, None, Any]):
    """Convert tool execution failures into tool messages so the run can continue."""

    state_schema = LeadAgentState
    tools: Sequence[BaseTool] = ()

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ) -> ToolMessage:
        try:
            return await handler(request)
        except ToolException as exc:
            tool_name = (
                _tool_name(request.tool) or request.tool_call.get("name") or "tool"
            )
            error_message = (
                f"Tool '{tool_name}' failed: {exc}. "
                "Continue without this result and try another source if needed."
            )
            return ToolMessage(
                content=error_message,
                tool_call_id=str(request.tool_call.get("id") or tool_name),
                status="error",
            )


def _render_enabled_skill_summaries(skills: Sequence[Any]) -> str:
    """Build the lightweight skill discovery prompt section."""
    skills_list = []
    for skill in skills:
        skills_list.append(
            f"- skill_id: {skill.skill_id} | name: {skill.name} | summary: {skill.description}"
        )
    if skills_list:
        skills_list = "\n".join(skills_list)
    else:
        skills_list = "No skills available."
    lines = """
    <Skill_system>
    You have access to skills that provide optimized workflows for specific tasks. Each skill contains best practices, frameworks, and references to additional resources.
    **Progressive Loading Pattern:**
    1. When the user's query relates to a skill summary, immediately call the `load_skill` function with the correct `skill_id` to load that skill.
    2. Follow the skill's instructions precisely
    <Available Skills>
    {skills_list}
    </Available Skills>
    </Skill_system>
    """

    return lines.format(skills_list=skills_list)


def _render_active_skill_prompt(skill: Any) -> str:
    """Build the activated skill prompt section."""
    return f"""
    <Active_skill>
    Active skill: {skill.skill_id} (version {skill.version})
    Activated instructions:
    {skill.activation_prompt.strip()}
    </Active_skill>
    """


def _visible_tool_names(
    *,
    active_skill_id: str | None,
    allowed_tool_names: Sequence[str],
    subagent_enabled: bool,
    delegation_depth: int,
) -> set[str]:
    """Resolve the visible tool names for the current model call."""
    if not active_skill_id:
        visible_tool_names = set(_BASE_SKILL_TOOL_NAMES)
    else:
        visible_tool_names = set(_BASE_SKILL_TOOL_NAMES).union(allowed_tool_names)

    if subagent_enabled and delegation_depth == 0:
        visible_tool_names.add(_DELEGATION_TOOL_NAME)

    return visible_tool_names


def _resolve_orchestration_prompt_update(
    state: dict[str, Any],
    *,
    existing_prompt: str | None,
) -> str | None:
    """Return the full system prompt content appropriate for the current run."""
    delegation_depth = _normalize_non_negative_int(state.get("delegation_depth"))
    if delegation_depth > 0:
        return get_lead_agent_worker_system_prompt()

    if _normalize_bool(state.get("subagent_enabled")):
        return _merge_system_prompt(
            existing_prompt,
            [get_lead_agent_orchestration_system_prompt()],
        )

    return None


def _tool_name(tool: BaseTool | dict[str, Any]) -> str | None:
    """Return a comparable tool name from a model request tool entry."""
    if isinstance(tool, dict):
        name = tool.get("name")
        if isinstance(name, str):
            return name
        return None
    return tool.name


def _merge_system_prompt(
    existing_prompt: str | None,
    prompt_sections: Sequence[str],
) -> str:
    """Merge the existing system prompt with skill-aware additions."""
    sections: list[str] = []
    if existing_prompt:
        sections.append(existing_prompt.strip())
    sections.extend(section.strip() for section in prompt_sections if section.strip())
    return "\n\n".join(sections)


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
    current_revision = _normalize_non_negative_int(state.get("todos_revision"))
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
        for status in _TODO_STATUSES
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


def _as_state_dict(state: Any) -> dict[str, Any]:
    """Normalize middleware state into a plain dict."""
    if isinstance(state, dict):
        return state
    return dict(state)


def _normalize_optional_string(value: Any) -> str | None:
    """Normalize one optional string value."""
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def _normalize_bool(value: Any) -> bool:
    """Normalize one flag-like value into a strict boolean."""
    return value is True


def _normalize_non_negative_int(value: Any) -> int:
    """Normalize one optional numeric value into a non-negative integer."""
    try:
        normalized_value = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, normalized_value)


def _normalize_unique_strings(values: Sequence[Any]) -> list[str]:
    """Normalize ordered strings while dropping blanks and duplicates."""
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized_value = str(value).strip()
        if not normalized_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values


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
        if not content or status not in _TODO_STATUSES:
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


def _get_lead_agent_skill_access_resolver() -> LeadAgentSkillAccessResolver:
    """Load the shared skill access resolver lazily to avoid import cycles."""
    from app.common.service import get_lead_agent_skill_access_resolver

    return get_lead_agent_skill_access_resolver()


def _build_lead_agent_summarization_triggers(
    model: BaseChatModel,
) -> list[tuple[str, int | float]]:
    """Build safe trigger thresholds for one resolved model profile."""
    triggers: list[tuple[str, int | float]] = [
        LEAD_AGENT_SUMMARIZATION_MESSAGE_TRIGGER,
        LEAD_AGENT_SUMMARIZATION_TOKEN_TRIGGER,
    ]
    profile = getattr(model, "profile", None)
    if isinstance(profile, dict) and isinstance(profile.get("max_input_tokens"), int):
        triggers.insert(0, LEAD_AGENT_SUMMARIZATION_FRACTION_TRIGGER)
    return triggers


def build_lead_agent_middleware(
    model: BaseChatModel,
) -> list[AgentMiddleware[Any, None, Any]]:
    """Build the ordered lead-agent middleware stack for one resolved model."""
    return [
        SummarizationMiddleware(
            model=model,
            trigger=_build_lead_agent_summarization_triggers(model),
            keep=LEAD_AGENT_SUMMARIZATION_KEEP,
            summary_prompt=get_lead_agent_summarization_prompt(),
            trim_tokens_to_summarize=LEAD_AGENT_SUMMARIZATION_TRIM_TOKENS,
        ),
        LeadAgentOrchestrationPromptMiddleware(),
        LeadAgentSkillPromptMiddleware(),
        LeadAgentTodoMiddleware(),
        LeadAgentDelegationLimitMiddleware(),
        LeadAgentToolSelectionMiddleware(),
        LeadAgentToolErrorMiddleware(),
    ]
