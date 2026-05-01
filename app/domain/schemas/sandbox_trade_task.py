"""Schemas for queued sandbox trade-agent worker tasks."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, TypeAdapter, field_validator

from app.domain.schemas.sandbox_trade_agent import SandboxTradeAgentSchemaBase
from app.domain.schemas.stock_research_report import MAX_STOCK_RESEARCH_SYMBOL_LENGTH


class SandboxTradeTickTask(SandboxTradeAgentSchemaBase):
    """Payload contract for one queued sandbox trade-agent tick."""

    session_id: str = Field(..., min_length=1)
    tick_id: str = Field(..., min_length=1)
    lock_token: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    tick_at: datetime
    retry_count: int = Field(default=0, ge=0)
    queued_at: datetime | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize queued symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


_SANDBOX_TRADE_TICK_TASK_ADAPTER = TypeAdapter(SandboxTradeTickTask)


def parse_sandbox_trade_tick_task(value: object) -> SandboxTradeTickTask:
    """Parse one queued sandbox trade task into its typed contract."""
    return _SANDBOX_TRADE_TICK_TASK_ADAPTER.validate_python(value)
