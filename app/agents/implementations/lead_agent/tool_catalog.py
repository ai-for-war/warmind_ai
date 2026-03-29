"""Shared selectable tool catalog for lead-agent runtime and public APIs."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from app.agents.implementations.lead_agent.tools import LEAD_AGENT_INTERNAL_TOOLS


@dataclass(frozen=True)
class LeadAgentSelectableToolDescriptor:
    """Public metadata for one selectable lead-agent tool."""

    tool_name: str
    display_name: str
    description: str
    category: str


@dataclass(frozen=True)
class _LeadAgentSelectableToolRegistration:
    """Internal registration entry linking tool metadata to runtime tools."""

    descriptor: LeadAgentSelectableToolDescriptor
    tool: BaseTool


_SELECTABLE_TOOL_REGISTRATIONS: list[_LeadAgentSelectableToolRegistration] = []


def get_lead_agent_selectable_tool_catalog() -> list[LeadAgentSelectableToolDescriptor]:
    """Return the selectable tool catalog that is actually available."""
    return [
        registration.descriptor for registration in _SELECTABLE_TOOL_REGISTRATIONS
    ]


def get_lead_agent_selectable_tool_names() -> set[str]:
    """Return the set of selectable tool names currently available."""
    return {
        descriptor.tool_name for descriptor in get_lead_agent_selectable_tool_catalog()
    }


def get_lead_agent_tools() -> list[BaseTool]:
    """Return the full runtime tool surface for lead-agent."""
    return LEAD_AGENT_INTERNAL_TOOLS + [
        registration.tool for registration in _SELECTABLE_TOOL_REGISTRATIONS
    ]
