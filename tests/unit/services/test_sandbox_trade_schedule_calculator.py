from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.stocks.sandbox_trade_schedule_calculator import (
    calculate_next_sandbox_trade_run_at,
    coerce_to_next_sandbox_trade_window,
    is_sandbox_trade_trading_time,
)


def _utc(
    year: int = 2026,
    month: int = 4,
    day: int = 27,
    hour: int = 2,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (_utc(2026, 4, 27, 2, 0), True),  # Monday 09:00 Asia/Saigon.
        (_utc(2026, 4, 27, 4, 30), True),  # Monday 11:30 Asia/Saigon.
        (_utc(2026, 4, 27, 5, 0), False),  # Monday lunch break.
        (_utc(2026, 4, 27, 6, 0), True),  # Monday 13:00 Asia/Saigon.
        (_utc(2026, 4, 27, 7, 45), True),  # Monday 14:45 Asia/Saigon.
        (_utc(2026, 4, 27, 8, 0), False),  # Monday after close.
        (_utc(2026, 5, 2, 2, 0), False),  # Saturday.
        (_utc(2026, 5, 3, 2, 0), False),  # Sunday.
    ],
)
def test_trading_time_uses_vietnam_continuous_windows(
    value: datetime,
    expected: bool,
) -> None:
    assert is_sandbox_trade_trading_time(value) is expected


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (_utc(2026, 4, 27, 1, 59), _utc(2026, 4, 27, 2, 2)),
        (_utc(2026, 4, 27, 2, 0), _utc(2026, 4, 27, 2, 3)),
        (_utc(2026, 4, 27, 4, 31), _utc(2026, 4, 27, 6, 0)),
        (_utc(2026, 4, 27, 7, 46), _utc(2026, 4, 28, 2, 0)),
        (_utc(2026, 5, 1, 7, 46), _utc(2026, 5, 4, 2, 0)),
        (_utc(2026, 5, 2, 2, 0), _utc(2026, 5, 4, 2, 0)),
        (_utc(2026, 5, 3, 2, 0), _utc(2026, 5, 4, 2, 0)),
    ],
)
def test_next_run_calculation_skips_breaks_close_and_weekends(
    after: datetime,
    expected: datetime,
) -> None:
    assert calculate_next_sandbox_trade_run_at(after=after) == expected


def test_next_run_can_include_current_when_already_inside_window() -> None:
    assert (
        calculate_next_sandbox_trade_run_at(
            after=_utc(2026, 4, 27, 2, 0),
            include_current=True,
        )
        == _utc(2026, 4, 27, 2, 0)
    )


def test_coerce_rejects_naive_reference_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        coerce_to_next_sandbox_trade_window(datetime(2026, 4, 27, 2, 0))
