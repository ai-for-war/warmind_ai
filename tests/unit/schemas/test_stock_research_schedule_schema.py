from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models.stock_research_schedule import (
    StockResearchScheduleStatus,
    StockResearchScheduleType,
    StockResearchScheduleWeekday,
)
from app.domain.schemas.stock_research_schedule import (
    StockResearchScheduleCreateRequest,
    StockResearchScheduleDefinitionRequest,
    StockResearchScheduleUpdateRequest,
)


def _runtime_config() -> dict[str, str]:
    return {
        "provider": "openai",
        "model": "gpt-5.2",
        "reasoning": "high",
    }


def test_every_15_minutes_schedule_accepts_type_only_definition() -> None:
    request = StockResearchScheduleCreateRequest(
        symbol=" fpt ",
        runtime_config=_runtime_config(),
        schedule={"type": "every_15_minutes"},
    )

    assert request.symbol == "FPT"
    assert (
        request.schedule.schedule_type
        == StockResearchScheduleType.EVERY_15_MINUTES
    )
    assert request.schedule.hour is None
    assert request.schedule.weekdays == []


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "every_15_minutes", "hour": 8},
        {"type": "every_15_minutes", "weekdays": ["monday"]},
        {"type": "daily"},
        {"type": "daily", "hour": 8, "weekdays": ["monday"]},
        {"type": "weekly", "hour": 8, "weekdays": []},
        {"type": "weekly", "weekdays": ["monday"]},
        {"type": "weekly", "hour": 24, "weekdays": ["monday"]},
    ],
)
def test_schedule_definition_rejects_invalid_shape(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StockResearchScheduleDefinitionRequest(**payload)


def test_daily_schedule_requires_integer_hour() -> None:
    schedule = StockResearchScheduleDefinitionRequest(type="daily", hour=8)

    assert schedule.schedule_type == StockResearchScheduleType.DAILY
    assert schedule.hour == 8
    assert schedule.weekdays == []


def test_weekly_schedule_accepts_multiple_normalized_unique_weekdays() -> None:
    schedule = StockResearchScheduleDefinitionRequest(
        type="weekly",
        hour=8,
        weekdays=[" Monday ", "wednesday", "MONDAY"],
    )

    assert schedule.schedule_type == StockResearchScheduleType.WEEKLY
    assert schedule.hour == 8
    assert schedule.weekdays == [
        StockResearchScheduleWeekday.MONDAY,
        StockResearchScheduleWeekday.WEDNESDAY,
    ]


def test_update_request_accepts_partial_schedule_changes() -> None:
    request = StockResearchScheduleUpdateRequest(
        symbol=" vcb ",
        status=StockResearchScheduleStatus.PAUSED,
    )

    assert request.symbol == "VCB"
    assert request.status == StockResearchScheduleStatus.PAUSED
    assert request.runtime_config is None
    assert request.schedule is None
