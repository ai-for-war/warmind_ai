"""Redis cache helpers for stock catalog default-list responses."""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError
from redis.asyncio import Redis

from app.domain.schemas.stock import StockListResponse

logger = logging.getLogger(__name__)


class StockCatalogCache:
    """Cache unfiltered stock list responses keyed by page and page size."""

    CACHE_TTL_SECONDS = 300
    KEY_PREFIX = "stocks:list"

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def _build_key(self, *, page: int, page_size: int) -> str:
        return f"{self.KEY_PREFIX}:page={page}:size={page_size}"

    async def get_page(
        self,
        *,
        page: int,
        page_size: int,
    ) -> StockListResponse | None:
        """Return one cached unfiltered stock page if available."""
        try:
            key = self._build_key(page=page, page_size=page_size)
            payload = await self.redis.get(key)
            if not payload:
                return None
            return StockListResponse.model_validate_json(payload)
        except (ConnectionError, TimeoutError, ValidationError, json.JSONDecodeError) as exc:
            logger.warning("Stock catalog cache get error: %s", exc)
            return None

    async def set_page(
        self,
        *,
        page: int,
        page_size: int,
        response: StockListResponse,
    ) -> None:
        """Cache one unfiltered stock page response."""
        try:
            key = self._build_key(page=page, page_size=page_size)
            await self.redis.setex(
                key,
                self.CACHE_TTL_SECONDS,
                response.model_dump_json(),
            )
        except (ConnectionError, TimeoutError, TypeError, ValueError) as exc:
            logger.warning("Stock catalog cache set error: %s", exc)

    async def invalidate_all(self) -> int:
        """Remove all cached unfiltered stock list pages."""
        try:
            keys: list[str] = []
            async for key in self.redis.scan_iter(match=f"{self.KEY_PREFIX}:*"):
                keys.append(key)
            if not keys:
                return 0
            return await self.redis.unlink(*keys)
        except (ConnectionError, TimeoutError) as exc:
            logger.warning("Stock catalog cache invalidation error: %s", exc)
            return 0
