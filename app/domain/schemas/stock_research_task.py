"""Schemas for queued stock research worker tasks."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, TypeAdapter, field_validator

from app.domain.schemas.stock_research_report import (
    MAX_STOCK_RESEARCH_SYMBOL_LENGTH,
    StockResearchReportRuntimeConfigResponse,
    StockResearchReportSchemaBase,
)


class StockResearchTask(StockResearchReportSchemaBase):
    """Payload contract for one queued stock research report task."""

    report_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    runtime_config: StockResearchReportRuntimeConfigResponse
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


_STOCK_RESEARCH_TASK_ADAPTER = TypeAdapter(StockResearchTask)


def parse_stock_research_task(value: object) -> StockResearchTask:
    """Parse one queued stock research task into its typed contract."""
    return _STOCK_RESEARCH_TASK_ADAPTER.validate_python(value)
