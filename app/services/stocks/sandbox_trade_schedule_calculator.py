"""Trading-window checks and next-run calculation for sandbox trade sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

SANDBOX_TRADE_TIMEZONE_NAME = "Asia/Saigon"
SANDBOX_TRADE_TIMEZONE = ZoneInfo(SANDBOX_TRADE_TIMEZONE_NAME)
DEFAULT_SANDBOX_TRADE_CADENCE_SECONDS = 180
DEFAULT_SANDBOX_TRADE_TRADING_WINDOWS = ("09:00-11:30", "13:00-14:45")


@dataclass(frozen=True)
class SandboxTradeTradingWindow:
    """One inclusive Vietnam continuous trading window."""

    start: time
    end: time

    def contains(self, value: time) -> bool:
        """Return whether one local time is inside this inclusive window."""
        return self.start <= value <= self.end


def parse_sandbox_trade_trading_windows(
    values: list[str] | tuple[str, ...] | None = None,
) -> tuple[SandboxTradeTradingWindow, ...]:
    """Parse configured trading windows in `HH:MM-HH:MM` format."""
    raw_windows = values or DEFAULT_SANDBOX_TRADE_TRADING_WINDOWS
    parsed: list[SandboxTradeTradingWindow] = []
    for raw_value in raw_windows:
        start_raw, separator, end_raw = raw_value.partition("-")
        if not separator:
            raise ValueError("trading windows must use HH:MM-HH:MM format")
        start = _parse_time(start_raw)
        end = _parse_time(end_raw)
        if start > end:
            raise ValueError("trading window start must be before end")
        parsed.append(SandboxTradeTradingWindow(start=start, end=end))

    if not parsed:
        raise ValueError("at least one trading window is required")
    return tuple(sorted(parsed, key=lambda window: window.start))


def is_sandbox_trade_weekday(value: datetime) -> bool:
    """Return whether one datetime falls on Monday-Friday in Vietnam time."""
    local_value = _require_aware_datetime(value).astimezone(SANDBOX_TRADE_TIMEZONE)
    return local_value.weekday() < 5


def is_sandbox_trade_trading_time(
    value: datetime,
    *,
    windows: tuple[SandboxTradeTradingWindow, ...] | None = None,
) -> bool:
    """Return whether one datetime is inside an eligible trading window."""
    local_value = _require_aware_datetime(value).astimezone(SANDBOX_TRADE_TIMEZONE)
    if local_value.weekday() >= 5:
        return False

    configured_windows = windows or parse_sandbox_trade_trading_windows()
    local_time = local_value.time().replace(tzinfo=None)
    return any(window.contains(local_time) for window in configured_windows)


def calculate_next_sandbox_trade_run_at(
    *,
    after: datetime,
    cadence_seconds: int = DEFAULT_SANDBOX_TRADE_CADENCE_SECONDS,
    windows: tuple[SandboxTradeTradingWindow, ...] | None = None,
    include_current: bool = False,
) -> datetime:
    """Return the next eligible UTC run time at or after one reference time."""
    if cadence_seconds <= 0:
        raise ValueError("cadence_seconds must be positive")

    configured_windows = windows or parse_sandbox_trade_trading_windows()
    normalized_after = _require_aware_datetime(after).astimezone(timezone.utc)

    if include_current and is_sandbox_trade_trading_time(
        normalized_after,
        windows=configured_windows,
    ):
        return normalized_after

    candidate = normalized_after + timedelta(seconds=cadence_seconds)
    return coerce_to_next_sandbox_trade_window(
        candidate,
        windows=configured_windows,
    )


def coerce_to_next_sandbox_trade_window(
    value: datetime,
    *,
    windows: tuple[SandboxTradeTradingWindow, ...] | None = None,
) -> datetime:
    """Move one datetime to the next eligible Vietnam trading-window timestamp."""
    configured_windows = windows or parse_sandbox_trade_trading_windows()
    local_value = _require_aware_datetime(value).astimezone(SANDBOX_TRADE_TIMEZONE)

    for day_offset in range(8):
        candidate_date = local_value.date() + timedelta(days=day_offset)
        if candidate_date.weekday() >= 5:
            continue

        for window in configured_windows:
            window_start = datetime.combine(
                candidate_date,
                window.start,
                tzinfo=SANDBOX_TRADE_TIMEZONE,
            )
            window_end = datetime.combine(
                candidate_date,
                window.end,
                tzinfo=SANDBOX_TRADE_TIMEZONE,
            )
            if day_offset == 0:
                if local_value < window_start:
                    return window_start.astimezone(timezone.utc)
                if window_start <= local_value <= window_end:
                    return local_value.astimezone(timezone.utc)
                continue
            return window_start.astimezone(timezone.utc)

    raise ValueError("unable to calculate next sandbox trade run time")


def _parse_time(value: str) -> time:
    """Parse one `HH:MM` value into a time object."""
    try:
        return time.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("trading window boundaries must use HH:MM format") from exc


def _require_aware_datetime(value: datetime) -> datetime:
    """Require timezone-aware datetimes for business-time calculations."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value
