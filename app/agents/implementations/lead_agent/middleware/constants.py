"""Shared constants for the lead-agent middleware package."""

from __future__ import annotations

from app.infrastructure.mcp.research_tools import RESEARCH_TOOL_NAMES

BASE_SKILL_TOOL_NAMES = {"load_skill", "write_todos", *RESEARCH_TOOL_NAMES}
DELEGATION_TOOL_NAME = "delegate_tasks"
LEAD_AGENT_SUMMARIZATION_MESSAGE_TRIGGER = ("messages", 30)
LEAD_AGENT_SUMMARIZATION_TOKEN_TRIGGER = ("tokens", 15564)
LEAD_AGENT_SUMMARIZATION_FRACTION_TRIGGER = ("fraction", 0.8)
LEAD_AGENT_SUMMARIZATION_KEEP = ("messages", 12)
LEAD_AGENT_SUMMARIZATION_TRIM_TOKENS = 15564
LEAD_AGENT_TODO_STATE_MAX_ITEMS = 20
LEAD_AGENT_TODO_REVISION_MARKER_PREFIX = "[todos_revision="
TODO_STATUSES = ("pending", "in_progress", "completed")
