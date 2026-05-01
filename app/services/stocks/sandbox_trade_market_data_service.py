"""Market-data snapshot preparation for sandbox trade-agent ticks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from fastapi import HTTPException

from app.domain.models.sandbox_trade_agent import (
    SandboxTradeMarketSnapshot,
    SandboxTradeSession,
    SandboxTradeTick,
)
from app.domain.schemas.stock_price import (
    DEFAULT_INTRADAY_PAGE_SIZE,
    StockPriceIntradayItem,
    StockPriceIntradayQuery,
)
from app.repo.sandbox_trade_agent_repo import SandboxTradeTickRepository
from app.services.stocks.price_service import StockPriceService
from app.services.stocks.sandbox_trade_schedule_calculator import (
    SANDBOX_TRADE_TIMEZONE,
    SandboxTradeTradingWindow,
    is_sandbox_trade_trading_time,
)

NO_FRESH_MARKET_DATA = "NO_FRESH_MARKET_DATA"
SANDBOX_MARKET_DATA_SOURCE = "VCI"
SANDBOX_MARKET_DATA_FRESHNESS_RULE = "same_vietnam_trading_window"


@dataclass(frozen=True)
class SandboxTradeMarketDataPreparation:
    """Result of preparing market data for one sandbox tick."""

    tick: SandboxTradeTick
    market_snapshot: SandboxTradeMarketSnapshot | None
    should_continue: bool


@dataclass(frozen=True)
class _LatestIntradayTrade:
    """Latest usable intraday trade candidate from the stock price service."""

    item: StockPriceIntradayItem
    observed_at: datetime


class SandboxTradeMarketDataService:
    """Fetch, validate, and persist market snapshots before agent invocation."""

    def __init__(
        self,
        *,
        price_service: StockPriceService,
        tick_repo: SandboxTradeTickRepository,
        windows: tuple[SandboxTradeTradingWindow, ...],
        page_size: int = DEFAULT_INTRADAY_PAGE_SIZE,
    ) -> None:
        self.price_service = price_service
        self.tick_repo = tick_repo
        self.windows = windows
        self.page_size = page_size

    async def prepare_tick_market_data(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        now: datetime | None = None,
    ) -> SandboxTradeMarketDataPreparation:
        """Persist a fresh market snapshot or skip the tick before agent work."""
        process_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        snapshot = await self.get_fresh_snapshot(
            symbol=session.symbol,
            now=process_now,
        )

        if tick.id is None or tick.lock_token is None:
            return SandboxTradeMarketDataPreparation(
                tick=tick,
                market_snapshot=snapshot,
                should_continue=snapshot is not None,
            )

        if snapshot is None:
            skipped_tick = await self.tick_repo.mark_skipped_no_fresh_market_data(
                tick_id=tick.id,
                lock_token=tick.lock_token,
                completed_at=process_now,
                skip_reason=NO_FRESH_MARKET_DATA,
            )
            return SandboxTradeMarketDataPreparation(
                tick=skipped_tick or tick,
                market_snapshot=None,
                should_continue=False,
            )

        updated_tick = await self.tick_repo.attach_market_snapshot(
            tick_id=tick.id,
            lock_token=tick.lock_token,
            market_snapshot=snapshot,
        )
        return SandboxTradeMarketDataPreparation(
            tick=updated_tick or tick,
            market_snapshot=snapshot,
            should_continue=True,
        )

    async def get_fresh_snapshot(
        self,
        *,
        symbol: str,
        now: datetime | None = None,
    ) -> SandboxTradeMarketSnapshot | None:
        """Return a fresh latest-price snapshot for one symbol when available."""
        process_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if not is_sandbox_trade_trading_time(process_now, windows=self.windows):
            return None

        try:
            response = await self.price_service.get_intraday(
                symbol,
                StockPriceIntradayQuery(
                    source=SANDBOX_MARKET_DATA_SOURCE,
                    page_size=self.page_size,
                ),
            )
        except HTTPException:
            return None

        latest_trade = self._latest_trade(response.items)
        if latest_trade is None:
            return None

        if not self._is_fresh_trade(
            observed_at=latest_trade.observed_at,
            now=process_now,
        ):
            return None

        latest_price = latest_trade.item.price
        if latest_price is None or latest_price <= 0:
            return None

        return SandboxTradeMarketSnapshot(
            symbol=response.symbol,
            source=response.source,
            latest_price=float(latest_price),
            observed_at=latest_trade.observed_at,
            summary={
                "cache_hit": response.cache_hit,
                "intraday_count": len(response.items),
                "latest_trade_time": latest_trade.observed_at.isoformat(),
                "latest_trade_volume": latest_trade.item.volume,
                "latest_match_type": latest_trade.item.match_type,
                "latest_trade_id": latest_trade.item.id,
                "freshness_rule": SANDBOX_MARKET_DATA_FRESHNESS_RULE,
            },
        )

    def _latest_trade(
        self,
        items: list[StockPriceIntradayItem],
    ) -> _LatestIntradayTrade | None:
        candidates: list[_LatestIntradayTrade] = []
        for item in items:
            observed_at = self._parse_intraday_time(item.time)
            if observed_at is None:
                continue
            if item.price is None or item.price <= 0:
                continue
            candidates.append(_LatestIntradayTrade(item=item, observed_at=observed_at))

        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate.observed_at)

    def _is_fresh_trade(self, *, observed_at: datetime, now: datetime) -> bool:
        local_observed = observed_at.astimezone(SANDBOX_TRADE_TIMEZONE)
        local_now = now.astimezone(SANDBOX_TRADE_TIMEZONE)
        if local_observed.date() != local_now.date():
            return False
        if observed_at > now:
            return False
        if not is_sandbox_trade_trading_time(observed_at, windows=self.windows):
            return False

        observed_window = self._matching_window(
            local_observed.time().replace(tzinfo=None)
        )
        current_window = self._matching_window(local_now.time().replace(tzinfo=None))
        return observed_window is not None and observed_window == current_window

    @staticmethod
    def _parse_intraday_time(value: str | None) -> datetime | None:
        """Parse the canonical intraday `time` field emitted by VnstockPriceGateway.

        The installed vnstock runtime normalizes VCI intraday data to a DataFrame
        with `time`, `price`, `volume`, `match_type`, and `id`. The app gateway
        serializes that canonical `time`; naive values are interpreted as
        Asia/Saigon because VCI intraday timestamps are localized there before
        serialization.
        """
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            parsed_date = _parse_iso_date(normalized)
            if parsed_date is None:
                return None
            parsed = datetime.combine(parsed_date, time.min)

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=SANDBOX_TRADE_TIMEZONE)
        return parsed.astimezone(timezone.utc)

    def _matching_window(self, value: time) -> SandboxTradeTradingWindow | None:
        for window in self.windows:
            if window.contains(value):
                return window
        return None


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
