"""Delegation executor for stock-agent worker orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Literal
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.implementations.stock_agent.runtime import (
    StockAgentRuntimeConfig,
    get_default_stock_agent_runtime_config,
)
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

STOCK_AGENT_WORKER_RECURSION_LIMIT = 200
WORKER_ORCHESTRATION_MODE = "worker"
DELEGATION_STATUS_COMPLETED = "completed"
DELEGATION_STATUS_FAILED = "failed"
DELEGATION_STATUS_REJECTED = "rejected"
WORKER_STATUS_COMPLETED = "completed"
WORKER_STATUS_FAILED = "failed"
WORKER_STATUS_TIMEOUT = "timeout"
GENERAL_WORKER_AGENT_ID = "general_worker"
EVENT_ANALYST_AGENT_ID = "event_analyst"
StockSubagentId = Literal["general_worker", "event_analyst"]


@dataclass(frozen=True)
class StockAgentSubagentDefinition:
    """Registered stock-agent subagent metadata."""

    agent_id: str
    description: str


STOCK_AGENT_SUBAGENT_REGISTRY: Mapping[str, StockAgentSubagentDefinition] = (
    MappingProxyType(
        {
            GENERAL_WORKER_AGENT_ID: StockAgentSubagentDefinition(
                agent_id=GENERAL_WORKER_AGENT_ID,
                description="Generic isolated stock-agent worker for delegated tasks without a preset specialist.",
            ),
            EVENT_ANALYST_AGENT_ID: StockAgentSubagentDefinition(
                agent_id=EVENT_ANALYST_AGENT_ID,
                description="Preset event analyst for stock-relevant news, events, catalysts, policy, macro, and industry impact.",
            ),
        }
    )
)


class DelegatedTaskInput(BaseModel):
    """Structured delegated task request accepted by the internal tool."""

    model_config = ConfigDict(extra="forbid")

    agent_id: StockSubagentId = Field(
        ...,
        description="Required target subagent id. Supported values: general_worker, event_analyst.",
    )
    objective: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Required task objective for the worker. State exactly what the subagent must accomplish.",
    )
    context: str | None = Field(
        default=None,
        max_length=8000,
        description="Optional supporting context, constraints, assumptions, or source material the worker should use while completing the task.",
    )


class StockAgentDelegationExecutor:
    """Execute delegated worker tasks in isolated stock-agent runtimes."""

    def __init__(
        self,
        *,
        parent_state: Mapping[str, Any],
        parent_tool_call_id: str,
        runtime_config: StockAgentRuntimeConfig | None = None,
        worker_agent: CompiledStateGraph | None = None,
        event_analyst_agent: CompiledStateGraph | None = None,
        worker_timeout_seconds: float | None = None,
        result_max_chars: int | None = None,
    ) -> None:
        settings = get_settings()
        self.parent_state = dict(parent_state)
        self.parent_tool_call_id = parent_tool_call_id
        self.runtime_config = runtime_config or _resolve_runtime_config_from_state(
            parent_state
        )
        self.worker_agent = worker_agent
        self.event_analyst_agent = event_analyst_agent
        self.worker_timeout_seconds = max(
            1.0,
            float(
                worker_timeout_seconds or settings.STOCK_AGENT_SUBAGENT_TIMEOUT_SECONDS
            ),
        )
        self.result_max_chars = max(
            200,
            int(result_max_chars or settings.STOCK_AGENT_DELEGATED_RESULT_MAX_CHARS),
        )

    @classmethod
    def from_parent_state(
        cls,
        *,
        parent_state: Mapping[str, Any],
        parent_tool_call_id: str,
    ) -> "StockAgentDelegationExecutor":
        """Build one executor from the parent runtime state."""
        return cls(
            parent_state=parent_state,
            parent_tool_call_id=parent_tool_call_id,
        )

    async def execute(
        self,
        task: DelegatedTaskInput | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Execute one delegated task and return the worker outcome."""
        delegation_depth = _normalize_non_negative_int(
            self.parent_state.get("delegation_depth")
        )
        if delegation_depth > 0:
            return {
                "status": DELEGATION_STATUS_REJECTED,
                "error": "delegate_tasks is only available to parent stock-agent runs.",
                "result": None,
            }

        try:
            normalized_task = _normalize_task(task)
        except ValidationError as exc:
            return {
                "status": DELEGATION_STATUS_REJECTED,
                "error": _validation_error_to_text(exc),
                "result": None,
            }

        if normalized_task.agent_id not in STOCK_AGENT_SUBAGENT_REGISTRY:
            return {
                "status": DELEGATION_STATUS_REJECTED,
                "error": f"Unsupported stock-agent subagent id: {normalized_task.agent_id}.",
                "result": None,
            }

        if normalized_task.agent_id == GENERAL_WORKER_AGENT_ID:
            worker_agent = self._get_worker_agent()
            result = await self._execute_one_task(
                worker_agent=worker_agent,
                task=normalized_task,
            )
        else:
            try:
                event_analyst_agent = self._get_event_analyst_agent()
            except Exception as exc:
                result = _worker_setup_failed_result(normalized_task, exc)
            else:
                result = await self._execute_one_task(
                    worker_agent=event_analyst_agent,
                    task=normalized_task,
                    payload=self._build_event_analyst_payload(task=normalized_task),
                )

        if result["status"] == WORKER_STATUS_COMPLETED:
            status = DELEGATION_STATUS_COMPLETED
        else:
            status = DELEGATION_STATUS_FAILED

        return {
            "status": status,
            "subagent_id": normalized_task.agent_id,
            "worker_timeout_seconds": self.worker_timeout_seconds,
            "result": result,
        }

    async def _execute_one_task(
        self,
        *,
        worker_agent: CompiledStateGraph,
        task: DelegatedTaskInput,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute one delegated worker task with timeout and failure capture."""
        execution_payload = dict(payload or self._build_worker_payload(task=task))
        thread_id = str(uuid4())
        try:
            final_state = await asyncio.wait_for(
                worker_agent.ainvoke(
                    execution_payload,
                    config={
                        "configurable": {"thread_id": thread_id},
                        "recursion_limit": STOCK_AGENT_WORKER_RECURSION_LIMIT,
                    },
                ),
                timeout=self.worker_timeout_seconds,
            )
            return {
                "status": WORKER_STATUS_COMPLETED,
                "subagent_id": task.agent_id,
                "objective": _truncate_text(task.objective, max_chars=240),
                "summary": _extract_final_response(final_state),
                "error": None,
            }
        except asyncio.TimeoutError:
            logger.warning(
                "Delegated worker timed out (parent_tool_call_id=%s)",
                self.parent_tool_call_id,
            )
            return {
                "status": WORKER_STATUS_TIMEOUT,
                "subagent_id": task.agent_id,
                "objective": _truncate_text(task.objective, max_chars=240),
                "summary": None,
                "error": f"Worker timed out after {self.worker_timeout_seconds:.0f}s.",
            }
        except Exception as exc:
            logger.exception(
                "Delegated worker failed (parent_tool_call_id=%s)",
                self.parent_tool_call_id,
            )
            return {
                "status": WORKER_STATUS_FAILED,
                "subagent_id": task.agent_id,
                "objective": _truncate_text(task.objective, max_chars=240),
                "summary": None,
                "error": _truncate_text(
                    str(exc).strip() or "Worker failed.", max_chars=400
                ),
            }

    def _build_worker_payload(
        self,
        *,
        task: DelegatedTaskInput,
    ) -> dict[str, Any]:
        """Build an isolated worker execution payload from one delegated task."""
        return {
            "messages": [
                {
                    "role": "user",
                    "content": _render_worker_task_message(
                        task=task,
                    ),
                }
            ],
            "user_id": _normalize_optional_string(self.parent_state.get("user_id"))
            or "",
            "organization_id": _normalize_optional_string(
                self.parent_state.get("organization_id")
            ),
            "runtime_provider": self.runtime_config.provider,
            "runtime_model": self.runtime_config.model,
            "runtime_reasoning": self.runtime_config.reasoning,
            "subagent_enabled": False,
            "orchestration_mode": WORKER_ORCHESTRATION_MODE,
            "delegation_depth": 1,
            "delegation_parent_run_id": self.parent_tool_call_id,
            "delegated_execution_metadata": {
                "parent_tool_call_id": self.parent_tool_call_id,
                "subagent_id": task.agent_id,
            },
            "enabled_skill_ids": _normalize_string_list(
                self.parent_state.get("enabled_skill_ids", [])
            ),
            "active_skill_id": None,
            "loaded_skills": [],
            "allowed_tool_names": [],
            "active_skill_version": None,
            "todos_revision": 0,
        }

    def _build_event_analyst_payload(
        self,
        *,
        task: DelegatedTaskInput,
    ) -> dict[str, Any]:
        """Build the minimal event analyst execution payload."""
        return {
            "messages": [
                {
                    "role": "user",
                    "content": _render_worker_task_message(
                        task=task,
                    ),
                }
            ],
            "delegation_depth": 1,
            "delegation_parent_run_id": self.parent_tool_call_id,
            "delegated_execution_metadata": {
                "parent_tool_call_id": self.parent_tool_call_id,
                "subagent_id": task.agent_id,
            },
        }

    def _get_worker_agent(self) -> CompiledStateGraph:
        """Return the compiled worker runtime for the current runtime config."""
        if self.worker_agent is not None:
            return self.worker_agent
        return _get_cached_worker_agent(self.runtime_config)

    def _get_event_analyst_agent(self) -> CompiledStateGraph:
        """Return the compiled event analyst runtime for the current runtime config."""
        if self.event_analyst_agent is not None:
            return self.event_analyst_agent
        return _get_cached_event_analyst_agent(self.runtime_config)


def _normalize_task(task: DelegatedTaskInput | Mapping[str, Any]) -> DelegatedTaskInput:
    """Normalize delegated tool input into one validated task model."""
    if isinstance(task, DelegatedTaskInput):
        return task
    return DelegatedTaskInput.model_validate(task)


@lru_cache(maxsize=8)
def _get_cached_worker_agent(
    runtime_config: StockAgentRuntimeConfig,
) -> CompiledStateGraph:
    """Compile and cache worker runtimes by resolved stock-agent config."""
    from app.agents.implementations.stock_agent.agent import create_stock_agent

    return create_stock_agent(runtime_config, subagent_enabled=False)


@lru_cache(maxsize=8)
def _get_cached_event_analyst_agent(
    runtime_config: StockAgentRuntimeConfig,
) -> CompiledStateGraph:
    """Compile and cache event analyst runtimes by resolved stock-agent config."""
    from app.agents.implementations.event_analyst.agent import (
        create_event_analyst_agent,
    )

    return create_event_analyst_agent(runtime_config)


def _resolve_runtime_config_from_state(
    state: Mapping[str, Any],
) -> StockAgentRuntimeConfig:
    """Resolve the worker runtime config from parent state with a safe fallback."""
    provider = _normalize_optional_string(state.get("runtime_provider"))
    model = _normalize_optional_string(state.get("runtime_model"))
    if provider is None or model is None:
        return get_default_stock_agent_runtime_config()

    return StockAgentRuntimeConfig(
        provider=provider,
        model=model,
        reasoning=_normalize_optional_string(state.get("runtime_reasoning")),
    )


def _render_worker_task_message(
    *,
    task: DelegatedTaskInput,
) -> str:
    """Render the delegated task into the isolated worker user message."""
    sections = [
        f"Objective:\n{task.objective.strip()}",
    ]
    if task.context:
        sections.append(f"Relevant context:\n{task.context.strip()}")
    sections.append(
        "Constraints:\nDo not ask the user for clarification. State assumptions or blockers explicitly and return a concise synthesis-ready result."
    )
    return "\n\n".join(sections)


def _worker_setup_failed_result(
    task: DelegatedTaskInput,
    exc: Exception,
) -> dict[str, Any]:
    """Return a bounded failure when a registered worker runtime cannot be built."""
    error_message = str(exc).strip() or "Worker runtime setup failed."
    return {
        "status": WORKER_STATUS_FAILED,
        "subagent_id": task.agent_id,
        "objective": _truncate_text(task.objective, max_chars=240),
        "summary": None,
        "error": _truncate_text(error_message, max_chars=400),
    }


def _validation_error_to_text(exc: ValidationError) -> str:
    """Convert delegated task validation errors into a bounded tool response."""
    messages: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ())) or "task"
        message = str(error.get("msg") or "Invalid value.")
        messages.append(f"{location}: {message}")
    if not messages:
        return "Invalid delegated task input."
    return _truncate_text("; ".join(messages), max_chars=400) or "Invalid delegated task input."


def _extract_final_response(result: Mapping[str, Any]) -> str:
    """Extract the final assistant response from one worker result state."""
    structured_response = (
        result.get("structured_response") if isinstance(result, Mapping) else None
    )
    if structured_response is not None:
        return _structured_response_to_text(structured_response)

    messages = result.get("messages") if isinstance(result, Mapping) else None
    if not messages:
        raise RuntimeError("Worker did not produce any messages.")

    for message in reversed(messages):
        if _is_assistant_message(message):
            response = _message_content_to_text(message)
            if response:
                return response

    fallback_response = _message_content_to_text(messages[-1])
    if fallback_response:
        return fallback_response
    raise RuntimeError("Worker did not produce a usable final response.")


def _structured_response_to_text(response: Any) -> str:
    """Serialize one structured worker response into a parent-readable string."""
    if hasattr(response, "model_dump_json"):
        return str(response.model_dump_json())
    if isinstance(response, Mapping):
        return json.dumps(dict(response), ensure_ascii=False)
    if isinstance(response, list):
        return json.dumps(response, ensure_ascii=False)
    return str(response).strip()


def _is_assistant_message(message: Any) -> bool:
    """Return True when one worker message is an assistant output."""
    if isinstance(message, Mapping):
        return message.get("role") == "assistant"
    if getattr(message, "type", None) == "ai":
        return True
    if getattr(message, "role", None) == "assistant":
        return True
    return message.__class__.__name__ == "AIMessage"


def _message_content_to_text(message: Any) -> str:
    """Normalize one worker message content payload into plain text."""
    if isinstance(message, Mapping):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    return _content_to_text(content).strip()


def _content_to_text(content: Any) -> str:
    """Convert structured content into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_content_to_text(item).strip() for item in content]
        return "\n".join(part for part in parts if part)
    if isinstance(content, Mapping):
        if content.get("text") is not None:
            return str(content["text"])
        if "content" in content:
            return _content_to_text(content["content"])
        return ""
    if content is None:
        return ""
    return str(content)


def _truncate_text(value: str | None, *, max_chars: int) -> str | None:
    """Bound one text field to a stable maximum size."""
    if value is None:
        return None
    normalized_value = value.strip()
    if len(normalized_value) <= max_chars:
        return normalized_value
    return normalized_value[: max_chars - 3].rstrip() + "..."


def _normalize_string_list(values: Sequence[Any]) -> list[str]:
    """Normalize ordered string collections while dropping blanks and duplicates."""
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized_value = str(value).strip()
        if not normalized_value or normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized_values.append(normalized_value)
    return normalized_values


def _normalize_optional_string(value: Any) -> str | None:
    """Normalize one optional string value."""
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def _normalize_non_negative_int(value: Any) -> int:
    """Normalize one optional integer into a non-negative value."""
    try:
        normalized_value = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, normalized_value)
