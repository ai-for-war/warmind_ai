from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.stocks.sandbox_trade_settlement_calculator import (
    calculate_sandbox_trade_settle_at,
)

VN_TZ = ZoneInfo("Asia/Saigon")


def _vn(
    year: int,
    month: int,
    day: int,
    hour: int = 10,
) -> datetime:
    return datetime(year, month, day, hour, tzinfo=VN_TZ)


@pytest.mark.parametrize(
    ("trade_at", "expected_local_date"),
    [
        (_vn(2026, 5, 4), "2026-05-06"),  # Monday -> Wednesday.
        (_vn(2026, 5, 5), "2026-05-07"),  # Tuesday -> Thursday.
        (_vn(2026, 5, 6), "2026-05-08"),  # Wednesday -> Friday.
        (_vn(2026, 5, 7), "2026-05-11"),  # Thursday -> Monday.
        (_vn(2026, 5, 8), "2026-05-12"),  # Friday -> Tuesday.
    ],
)
def test_t_plus_two_counts_weekdays_only(
    trade_at: datetime,
    expected_local_date: str,
) -> None:
    settled_at = calculate_sandbox_trade_settle_at(trade_at=trade_at)

    assert settled_at.astimezone(VN_TZ).date().isoformat() == expected_local_date
    assert settled_at.astimezone(VN_TZ).time().isoformat() == "00:00:00"


def test_settlement_calculator_rejects_naive_trade_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        calculate_sandbox_trade_settle_at(trade_at=datetime(2026, 5, 4, 10))
