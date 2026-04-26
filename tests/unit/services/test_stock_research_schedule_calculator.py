from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.models.stock_research_schedule import (
    StockResearchScheduleType,
    StockResearchScheduleWeekday,
)
from app.services.stocks.stock_research_schedule_calculator import (
    calculate_next_stock_research_run_at,
)


def _utc(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (_utc(2026, 4, 24, 0, 59), _utc(2026, 4, 24, 1, 0)),
        (_utc(2026, 4, 24, 1, 0), _utc(2026, 4, 24, 1, 15)),
        (_utc(2026, 4, 24, 1, 1), _utc(2026, 4, 24, 1, 15)),
    ],
)
def test_every_15_minutes_returns_next_quarter_hour(
    after: datetime,
    expected: datetime,
) -> None:
    assert (
        calculate_next_stock_research_run_at(
            schedule_type=StockResearchScheduleType.EVERY_15_MINUTES,
            after=after,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        # 07:30 Asia/Saigon before the configured 08:00 run.
        (_utc(2026, 4, 24, 0, 30), _utc(2026, 4, 24, 1, 0)),
        # 08:00 Asia/Saigon exactly advances strictly to the next day.
        (_utc(2026, 4, 24, 1, 0), _utc(2026, 4, 25, 1, 0)),
        # 09:00 Asia/Saigon after the configured run also advances next day.
        (_utc(2026, 4, 24, 2, 0), _utc(2026, 4, 25, 1, 0)),
    ],
)
def test_daily_schedule_uses_asia_saigon_hour(
    after: datetime,
    expected: datetime,
) -> None:
    assert (
        calculate_next_stock_research_run_at(
            schedule_type=StockResearchScheduleType.DAILY,
            hour=8,
            after=after,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        # Tuesday 07:00 Asia/Saigon -> Wednesday 08:00 Asia/Saigon.
        (_utc(2026, 4, 21, 0, 0), _utc(2026, 4, 22, 1, 0)),
        # Wednesday 08:00 Asia/Saigon exactly -> next Monday 08:00.
        (_utc(2026, 4, 22, 1, 0), _utc(2026, 4, 27, 1, 0)),
        # Monday 09:00 Asia/Saigon -> Wednesday 08:00.
        (_utc(2026, 4, 27, 2, 0), _utc(2026, 4, 29, 1, 0)),
    ],
)
def test_weekly_schedule_uses_multiple_asia_saigon_weekdays(
    after: datetime,
    expected: datetime,
) -> None:
    assert (
        calculate_next_stock_research_run_at(
            schedule_type=StockResearchScheduleType.WEEKLY,
            hour=8,
            weekdays=[
                StockResearchScheduleWeekday.MONDAY,
                StockResearchScheduleWeekday.WEDNESDAY,
            ],
            after=after,
        )
        == expected
    )


def test_calculator_rejects_naive_reference_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        calculate_next_stock_research_run_at(
            schedule_type=StockResearchScheduleType.DAILY,
            hour=8,
            after=datetime(2026, 4, 24, 1, 0),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "schedule_type": StockResearchScheduleType.EVERY_15_MINUTES,
            "hour": 8,
        },
        {
            "schedule_type": StockResearchScheduleType.DAILY,
            "hour": 8,
            "weekdays": [StockResearchScheduleWeekday.MONDAY],
        },
        {
            "schedule_type": StockResearchScheduleType.WEEKLY,
            "hour": 8,
            "weekdays": [],
        },
        {
            "schedule_type": StockResearchScheduleType.WEEKLY,
            "weekdays": [StockResearchScheduleWeekday.MONDAY],
        },
    ],
)
def test_calculator_rejects_invalid_schedule_shapes(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        calculate_next_stock_research_run_at(after=_utc(2026, 4, 24, 1), **kwargs)
