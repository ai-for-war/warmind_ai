"""Lead-agent state schema."""

from langchain.agents import AgentState


class LeadAgentState(AgentState):
    """Thread-scoped state for the lead-agent runtime."""

    user_id: str
    organization_id: str | None
