"""Redis cache helpers for stock company information responses."""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class StockCompanyCache:
    """Cache stock company information responses keyed by symbol and section."""

    CACHE_TTL_SECONDS = 86400
    KEY_PREFIX = "stocks:company"

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def _build_key(
        self,
        *,
        symbol: str,
        section: str,
        variant: str | None = None,
    ) -> str:
        normalized_symbol = symbol.strip().upper()
        base_key = f"{self.KEY_PREFIX}:{normalized_symbol}:{section}"
        if variant is None:
            return base_key
        return f"{base_key}:{variant}"

    async def get_response(
        self,
        *,
        symbol: str,
        section: str,
        response_model: type[ResponseModelT],
        variant: str | None = None,
    ) -> ResponseModelT | None:
        """Return one cached company response if available."""
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
            logger.warning("Stock company cache get error: %s", exc)
            return None

    async def set_response(
        self,
        *,
        symbol: str,
        section: str,
        response: BaseModel,
        variant: str | None = None,
    ) -> None:
        """Cache one company response."""
        try:
            key = self._build_key(symbol=symbol, section=section, variant=variant)
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
            logger.warning("Stock company cache set error: %s", exc)

    async def invalidate_symbol(self, symbol: str) -> int:
        """Remove cached company responses for one symbol."""
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
            logger.warning("Stock company cache invalidation error: %s", exc)
            return 0
