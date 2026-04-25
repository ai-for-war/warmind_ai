"""Schemas for stock research schedule request and response payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.domain.models.stock_research_schedule import (
    StockResearchScheduleStatus,
    StockResearchScheduleType,
    StockResearchScheduleWeekday,
)
from app.domain.schemas.stock_research_report import (
    MAX_STOCK_RESEARCH_SYMBOL_LENGTH,
    StockResearchReportRuntimeConfigRequest,
    StockResearchReportRuntimeConfigResponse,
    StockResearchReportSchemaBase,
)


class StockResearchScheduleDefinitionRequest(StockResearchReportSchemaBase):
    """Requested recurring schedule definition for stock research."""

    model_config = ConfigDict(populate_by_name=True)

    schedule_type: StockResearchScheduleType = Field(..., alias="type")
    hour: int | None = Field(default=None, ge=0, le=23)
    weekdays: list[StockResearchScheduleWeekday] = Field(default_factory=list)

    @field_validator("weekdays", mode="before")
    @classmethod
    def normalize_weekdays(cls, value: object) -> object:
        """Normalize weekday strings before enum parsing."""
        if value is None:
            return []
        if not isinstance(value, list):
            return value

        normalized: list[object] = []
        for item in value:
            if isinstance(item, str):
                normalized.append(item.strip().lower())
            else:
                normalized.append(item)
        return normalized

    @field_validator("weekdays")
    @classmethod
    def deduplicate_weekdays(
        cls,
        value: list[StockResearchScheduleWeekday],
    ) -> list[StockResearchScheduleWeekday]:
        """Deduplicate weekdays while preserving client order."""
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_shape(self) -> "StockResearchScheduleDefinitionRequest":
        """Require schedule fields to match the selected recurrence type."""
        if self.schedule_type == StockResearchScheduleType.EVERY_15_MINUTES:
            if self.hour is not None:
                raise ValueError("every_15_minutes schedules must not include hour")
            if self.weekdays:
                raise ValueError(
                    "every_15_minutes schedules must not include weekdays"
                )
            return self

        if self.schedule_type == StockResearchScheduleType.DAILY:
            if self.hour is None:
                raise ValueError("daily schedules require hour")
            if self.weekdays:
                raise ValueError("daily schedules must not include weekdays")
            return self

        if self.schedule_type == StockResearchScheduleType.WEEKLY:
            if self.hour is None:
                raise ValueError("weekly schedules require hour")
            if not self.weekdays:
                raise ValueError("weekly schedules require at least one weekday")
            return self

        raise ValueError("unsupported stock research schedule type")


class StockResearchScheduleDefinitionResponse(StockResearchReportSchemaBase):
    """Recurring schedule definition returned by stock research schedule APIs."""

    model_config = ConfigDict(populate_by_name=True)

    schedule_type: StockResearchScheduleType = Field(..., alias="type")
    hour: int | None = Field(default=None, ge=0, le=23)
    weekdays: list[StockResearchScheduleWeekday] = Field(default_factory=list)


class StockResearchScheduleCreateRequest(StockResearchReportSchemaBase):
    """Request payload for creating one recurring stock research schedule."""

    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    runtime_config: StockResearchReportRuntimeConfigRequest
    schedule: StockResearchScheduleDefinitionRequest

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize requested symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class StockResearchScheduleUpdateRequest(StockResearchReportSchemaBase):
    """Request payload for updating one recurring stock research schedule."""

    symbol: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH,
    )
    runtime_config: StockResearchReportRuntimeConfigRequest | None = None
    schedule: StockResearchScheduleDefinitionRequest | None = None
    status: StockResearchScheduleStatus | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_optional_symbol(cls, value: str | None) -> str | None:
        """Normalize optional requested symbols into uppercase canonical form."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("symbol must be a string or None")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class StockResearchScheduleSummary(StockResearchReportSchemaBase):
    """Common stock research schedule fields returned by schedule APIs."""

    id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    status: StockResearchScheduleStatus
    schedule: StockResearchScheduleDefinitionResponse
    next_run_at: datetime
    created_at: datetime
    updated_at: datetime
    runtime_config: StockResearchReportRuntimeConfigResponse

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize response symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class StockResearchScheduleResponse(StockResearchScheduleSummary):
    """Full response payload for one stock research schedule."""


class StockResearchScheduleListResponse(StockResearchReportSchemaBase):
    """Response returned by the stock research schedule list endpoint."""

    items: list[StockResearchScheduleSummary] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)


class StockResearchScheduleDeleteResponse(StockResearchReportSchemaBase):
    """Response payload for successful stock research schedule deletion."""

    id: str = Field(..., min_length=1)
    deleted: bool = True
