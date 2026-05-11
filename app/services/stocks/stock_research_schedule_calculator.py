"""Next-run calculation for stock research schedules."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain.models.stock_research_schedule import (
    StockResearchScheduleType,
    StockResearchScheduleWeekday,
)

STOCK_RESEARCH_SCHEDULE_TIMEZONE_NAME = "Asia/Ho_Chi_Minh"
STOCK_RESEARCH_SCHEDULE_TIMEZONE = ZoneInfo(STOCK_RESEARCH_SCHEDULE_TIMEZONE_NAME)

_WEEKDAY_INDEX: dict[StockResearchScheduleWeekday, int] = {
    StockResearchScheduleWeekday.MONDAY: 0,
    StockResearchScheduleWeekday.TUESDAY: 1,
    StockResearchScheduleWeekday.WEDNESDAY: 2,
    StockResearchScheduleWeekday.THURSDAY: 3,
    StockResearchScheduleWeekday.FRIDAY: 4,
    StockResearchScheduleWeekday.SATURDAY: 5,
    StockResearchScheduleWeekday.SUNDAY: 6,
}


def calculate_next_stock_research_run_at(
    *,
    schedule_type: StockResearchScheduleType,
    after: datetime,
    hour: int | None = None,
    weekdays: list[StockResearchScheduleWeekday] | None = None,
) -> datetime:
    """Return the next UTC occurrence strictly after one reference datetime."""
    normalized_after = _require_aware_datetime(after).astimezone(timezone.utc)

    if schedule_type == StockResearchScheduleType.EVERY_15_MINUTES:
        _validate_interval_schedule(hour=hour, weekdays=weekdays)
        return _next_quarter_hour_after(normalized_after)

    local_after = normalized_after.astimezone(STOCK_RESEARCH_SCHEDULE_TIMEZONE)

    if schedule_type == StockResearchScheduleType.DAILY:
        _validate_calendar_schedule(hour=hour, weekdays=weekdays, weekly=False)
        return _next_daily_after(local_after=local_after, hour=hour)

    if schedule_type == StockResearchScheduleType.WEEKLY:
        normalized_weekdays = _validate_calendar_schedule(
            hour=hour,
            weekdays=weekdays,
            weekly=True,
        )
        return _next_weekly_after(
            local_after=local_after,
            hour=hour,
            weekdays=normalized_weekdays,
        )

    raise ValueError("unsupported stock research schedule type")


def _next_quarter_hour_after(after_utc: datetime) -> datetime:
    """Return the next 15-minute UTC boundary strictly after the reference."""
    base = after_utc.replace(second=0, microsecond=0)
    minutes_to_add = 15 - (base.minute % 15)
    if minutes_to_add == 0:
        minutes_to_add = 15
    return base + timedelta(minutes=minutes_to_add)


def _next_daily_after(*, local_after: datetime, hour: int | None) -> datetime:
    """Return the next daily local occurrence as UTC."""
    if hour is None:
        raise ValueError("daily schedules require hour")

    candidate = datetime.combine(
        local_after.date(),
        time(hour=hour),
        tzinfo=STOCK_RESEARCH_SCHEDULE_TIMEZONE,
    )
    if candidate <= local_after:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def _next_weekly_after(
    *,
    local_after: datetime,
    hour: int | None,
    weekdays: list[StockResearchScheduleWeekday],
) -> datetime:
    """Return the next weekly local occurrence as UTC."""
    if hour is None:
        raise ValueError("weekly schedules require hour")

    candidates: list[datetime] = []
    for weekday in weekdays:
        days_ahead = (_WEEKDAY_INDEX[weekday] - local_after.weekday()) % 7
        candidate_date = local_after.date() + timedelta(days=days_ahead)
        candidate = datetime.combine(
            candidate_date,
            time(hour=hour),
            tzinfo=STOCK_RESEARCH_SCHEDULE_TIMEZONE,
        )
        if candidate <= local_after:
            candidate += timedelta(days=7)
        candidates.append(candidate)

    if not candidates:
        raise ValueError("weekly schedules require at least one weekday")
    return min(candidates).astimezone(timezone.utc)


def _validate_interval_schedule(
    *,
    hour: int | None,
    weekdays: list[StockResearchScheduleWeekday] | None,
) -> None:
    """Validate fields allowed for fixed interval schedules."""
    if hour is not None:
        raise ValueError("every_15_minutes schedules must not include hour")
    if weekdays:
        raise ValueError("every_15_minutes schedules must not include weekdays")


def _validate_calendar_schedule(
    *,
    hour: int | None,
    weekdays: list[StockResearchScheduleWeekday] | None,
    weekly: bool,
) -> list[StockResearchScheduleWeekday]:
    """Validate fields required for daily and weekly calendar schedules."""
    if hour is None:
        raise ValueError("calendar schedules require hour")
    if hour < 0 or hour > 23:
        raise ValueError("hour must be between 0 and 23")

    normalized_weekdays = list(dict.fromkeys(weekdays or []))
    if weekly:
        if not normalized_weekdays:
            raise ValueError("weekly schedules require at least one weekday")
        return normalized_weekdays

    if normalized_weekdays:
        raise ValueError("daily schedules must not include weekdays")
    return []


def _require_aware_datetime(value: datetime) -> datetime:
    """Require timezone-aware datetimes for schedule calculation."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("after must be timezone-aware")
    return value
