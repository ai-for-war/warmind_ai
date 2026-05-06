"""Structured output validation for sandbox trade-agent decisions."""

from __future__ import annotations

import json
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.domain.models.sandbox_trade_agent import (
    SandboxTradeAction,
    SandboxTradeDecision,
    SandboxTradeQuantityType,
)

INVALID_AGENT_DECISION = "INVALID_AGENT_DECISION"


class SandboxTradeAgentDecisionOutput(BaseModel):
    """Canonical structured decision returned by the sandbox trade agent."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    action: SandboxTradeAction
    quantity_type: SandboxTradeQuantityType | None = None
    quantity_value: float | None = Field(default=None, gt=0)
    reason: str = Field(..., min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_quantity_contract(self) -> "SandboxTradeAgentDecisionOutput":
        """Validate action-specific quantity fields before execution."""
        if self.action == SandboxTradeAction.HOLD:
            if self.quantity_type is not None or self.quantity_value is not None:
                raise ValueError("HOLD decisions must not include quantity fields")
            return self

        if self.quantity_type is None or self.quantity_value is None:
            raise ValueError("BUY and SELL decisions require quantity fields")

        if (
            self.action == SandboxTradeAction.BUY
            and self.quantity_type == SandboxTradeQuantityType.PERCENT_POSITION
        ):
            raise ValueError("BUY decisions cannot use percent_position quantity")

        if (
            self.action == SandboxTradeAction.SELL
            and self.quantity_type == SandboxTradeQuantityType.PERCENT_CASH
        ):
            raise ValueError("SELL decisions cannot use percent_cash quantity")

        return self

    def to_domain_model(self) -> SandboxTradeDecision:
        """Convert validated structured output into a persisted domain model."""
        return SandboxTradeDecision(
            action=self.action,
            quantity_type=self.quantity_type,
            quantity_value=self.quantity_value,
            reason=self.reason,
            confidence=self.confidence,
            risk_notes=self.risk_notes,
        )


_SANDBOX_TRADE_DECISION_ADAPTER = TypeAdapter(SandboxTradeAgentDecisionOutput)


def parse_sandbox_trade_decision_output(
    payload: SandboxTradeAgentDecisionOutput | Mapping[str, Any] | str,
) -> SandboxTradeAgentDecisionOutput:
    """Parse and validate one sandbox trade-agent structured decision."""
    if isinstance(payload, SandboxTradeAgentDecisionOutput):
        return payload
    if isinstance(payload, Mapping):
        return _SANDBOX_TRADE_DECISION_ADAPTER.validate_python(dict(payload))
    if not isinstance(payload, str):
        raise TypeError("sandbox trade decision must be a JSON string or mapping")

    normalized_payload = payload.strip()
    if not normalized_payload:
        raise ValueError("sandbox trade decision must not be blank")
    if normalized_payload.startswith("```"):
        normalized_payload = _strip_code_fence(normalized_payload)

    parsed_payload = json.loads(normalized_payload)
    return _SANDBOX_TRADE_DECISION_ADAPTER.validate_python(parsed_payload)


def _strip_code_fence(value: str) -> str:
    """Extract fenced JSON when a model wraps the structured answer."""
    lines = value.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return value
