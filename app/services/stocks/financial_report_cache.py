"""Redis cache helpers for stock financial report responses."""

from __future__ import annotations

import logging

from pydantic import ValidationError
from redis.asyncio import Redis

from app.domain.schemas.stock_financial_report import StockFinancialReportResponse

logger = logging.getLogger(__name__)


class StockFinancialReportCache:
    """Cache financial report responses keyed by symbol, report type, and period."""

    CACHE_TTL_SECONDS = 86400
    KEY_PREFIX = "stocks:financial-reports"

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def _build_key(self, *, symbol: str, report_type: str, period: str) -> str:
        normalized_symbol = symbol.strip().upper()
        normalized_report_type = report_type.strip().lower()
        normalized_period = period.strip().lower()
        return (
            f"{self.KEY_PREFIX}:{normalized_symbol}:"
            f"{normalized_report_type}:period={normalized_period}"
        )

    async def get_response(
        self,
        *,
        symbol: str,
        report_type: str,
        period: str,
    ) -> StockFinancialReportResponse | None:
        """Return one cached financial report response if available."""
        try:
            key = self._build_key(
                symbol=symbol,
                report_type=report_type,
                period=period,
            )
            payload = await self.redis.get(key)
            if not payload:
                return None
            return StockFinancialReportResponse.model_validate_json(payload)
        except (
            ConnectionError,
            TimeoutError,
            ValidationError,
            ValueError,
            TypeError,
            AttributeError,
        ) as exc:
            logger.warning("Stock financial report cache get error: %s", exc)
            return None

    async def set_response(
        self,
        *,
        symbol: str,
        report_type: str,
        period: str,
        response: StockFinancialReportResponse,
    ) -> None:
        """Cache one financial report response."""
        try:
            key = self._build_key(
                symbol=symbol,
                report_type=report_type,
                period=period,
            )
            await self.redis.setex(
                key,
                self.CACHE_TTL_SECONDS,
                response.model_dump_json(),
            )
        except (
            ConnectionError,
            TimeoutError,
            TypeError,
            ValueError,
            AttributeError,
        ) as exc:
            logger.warning("Stock financial report cache set error: %s", exc)

    async def invalidate_symbol(self, symbol: str) -> int:
        """Remove cached financial report responses for one symbol."""
        try:
            normalized_symbol = symbol.strip().upper()
            keys: list[str] = []
            async for key in self.redis.scan_iter(
                match=f"{self.KEY_PREFIX}:{normalized_symbol}:*"
            ):
                keys.append(key)
            if not keys:
                return 0
            return await self.redis.unlink(*keys)
        except (ConnectionError, TimeoutError, AttributeError) as exc:
            logger.warning("Stock financial report cache invalidation error: %s", exc)
            return 0
