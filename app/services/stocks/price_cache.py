"""Redis cache helpers for stock price history and intraday responses."""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class StockPriceCache:
    """Cache stock price responses keyed by symbol, section, and query variant."""

    HISTORY_CACHE_TTL_SECONDS = 86400
    INTRADAY_CACHE_TTL_SECONDS = 120
    KEY_PREFIX = "stocks:prices"

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def _build_key(self, *, symbol: str, section: str, variant: str) -> str:
        normalized_symbol = symbol.strip().upper()
        return f"{self.KEY_PREFIX}:{normalized_symbol}:{section}:{variant}"

    def _get_ttl(self, *, section: str) -> int:
        if section == "intraday":
            return self.INTRADAY_CACHE_TTL_SECONDS
        return self.HISTORY_CACHE_TTL_SECONDS

    async def get_response(
        self,
        *,
        symbol: str,
        section: str,
        variant: str,
        response_model: type[ResponseModelT],
    ) -> ResponseModelT | None:
        """Return one cached price response if available."""
        try:
            key = self._build_key(symbol=symbol, section=section, variant=variant)
            payload = await self.redis.get(key)
            if not payload:
                return None
            return response_model.model_validate_json(payload)
        except (
            ConnectionError,
            TimeoutError,
            ValidationError,
            ValueError,
            TypeError,
            AttributeError,
        ) as exc:
            logger.warning("Stock price cache get error: %s", exc)
            return None

    async def set_response(
        self,
        *,
        symbol: str,
        section: str,
        variant: str,
        response: BaseModel,
    ) -> None:
        """Cache one stock price response."""
        try:
            key = self._build_key(symbol=symbol, section=section, variant=variant)
            await self.redis.setex(
                key,
                self._get_ttl(section=section),
                response.model_dump_json(),
            )
        except (
            ConnectionError,
            TimeoutError,
            TypeError,
            ValueError,
            AttributeError,
        ) as exc:
            logger.warning("Stock price cache set error: %s", exc)

    async def invalidate_symbol(self, symbol: str) -> int:
        """Remove cached price responses for one symbol."""
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
            logger.warning("Stock price cache invalidation error: %s", exc)
            return 0
