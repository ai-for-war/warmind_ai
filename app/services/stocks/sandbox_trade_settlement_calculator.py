"""Weekday-only settlement calculations for sandbox trading."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from app.services.stocks.sandbox_trade_schedule_calculator import (
    SANDBOX_TRADE_TIMEZONE,
)


def calculate_sandbox_trade_settle_at(
    *,
    trade_at: datetime,
    settlement_weekdays: int = 2,
) -> datetime:
    """Return the UTC datetime when a weekday-only T+2 settlement becomes due."""
    if settlement_weekdays < 0:
        raise ValueError("settlement_weekdays must be non-negative")
    if trade_at.tzinfo is None or trade_at.utcoffset() is None:
        raise ValueError("trade_at must be timezone-aware")

    local_trade_at = trade_at.astimezone(SANDBOX_TRADE_TIMEZONE)
    settle_date = local_trade_at.date()
    remaining = settlement_weekdays

    while remaining > 0:
        settle_date += timedelta(days=1)
        if settle_date.weekday() < 5:
            remaining -= 1

    local_settle_at = datetime.combine(
        settle_date,
        time.min,
        tzinfo=SANDBOX_TRADE_TIMEZONE,
    )
    return local_settle_at.astimezone(timezone.utc)
