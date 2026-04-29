"""Service layer for stock price history and intraday reads."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.domain.schemas.stock_price import (
    StockPriceHistoryQuery,
    StockPriceHistoryResponse,
    StockPriceIntradayQuery,
    StockPriceIntradayResponse,
)
from app.repo.stock_symbol_repo import StockSymbolRepository
from app.services.stocks.price_cache import StockPriceCache
from app.services.stocks.price_gateway import VnstockPriceGateway

logger = logging.getLogger(__name__)

_USER_INPUT_ERROR_SNIPPETS: tuple[str, ...] = (
    "interval không hợp lệ",
    "định dạng ngày không hợp lệ",
    "thời gian bắt đầu không thể lớn hơn",
    "tham số 'start' là bắt buộc",
    'tham số "start" là bắt buộc',
    "không tìm thấy dữ liệu",
)


class StockPriceService:
    """Coordinate symbol validation, cache usage, and upstream price reads."""

    def __init__(
        self,
        repository: StockSymbolRepository,
        gateway: VnstockPriceGateway,
        cache: StockPriceCache,
    ) -> None:
        self.repository = repository
        self.gateway = gateway
        self.cache = cache

    async def get_history(
        self,
        symbol: str,
        query: StockPriceHistoryQuery,
    ) -> StockPriceHistoryResponse:
        normalized_query = StockPriceHistoryQuery.model_validate(query)
        variant = self._build_history_variant(normalized_query)
        normalized_symbol = await self._validate_symbol(symbol)

        cached = await self._get_cached_section(
            symbol=normalized_symbol,
            section="history",
            variant=variant,
            response_model=StockPriceHistoryResponse,
        )
        if cached is not None:
            return cached

        try:
            items = await run_in_threadpool(
                self.gateway.fetch_history,
                normalized_symbol,
                source=normalized_query.source,
                start=normalized_query.start,
                end=normalized_query.end,
                interval=normalized_query.interval,
                length=normalized_query.length,
            )
            response = StockPriceHistoryResponse(
                symbol=normalized_symbol,
                source=normalized_query.source,
                cache_hit=False,
                interval=normalized_query.interval,
                items=items,
            )
        except Exception as exc:
            stale = await self._get_cached_section(
                symbol=normalized_symbol,
                section="history",
                variant=variant,
                response_model=StockPriceHistoryResponse,
            )
            if stale is not None:
                return stale
            raise self._map_fetch_error(exc) from exc

        await self._set_cached_section(
            symbol=normalized_symbol,
            section="history",
            variant=variant,
            response=response,
        )
        return response

    async def get_intraday(
        self,
        symbol: str,
        query: StockPriceIntradayQuery,
    ) -> StockPriceIntradayResponse:
        normalized_query = StockPriceIntradayQuery.model_validate(query)
        self._validate_intraday_source_contract(normalized_query)
        variant = self._build_intraday_variant(normalized_query)
        normalized_symbol = await self._validate_symbol(symbol)

        cached = await self._get_cached_section(
            symbol=normalized_symbol,
            section="intraday",
            variant=variant,
            response_model=StockPriceIntradayResponse,
        )
        if cached is not None:
            return cached

        try:
            items = await run_in_threadpool(
                self.gateway.fetch_intraday,
                normalized_symbol,
                source=normalized_query.source,
                page_size=normalized_query.page_size,
                last_time=normalized_query.last_time,
                last_time_format=normalized_query.last_time_format,
            )
            response = StockPriceIntradayResponse(
                symbol=normalized_symbol,
                source=normalized_query.source,
                cache_hit=False,
                items=items,
            )
        except Exception as exc:
            stale = await self._get_cached_section(
                symbol=normalized_symbol,
                section="intraday",
                variant=variant,
                response_model=StockPriceIntradayResponse,
            )
            if stale is not None:
                return stale
            raise self._map_fetch_error(exc) from exc

        await self._set_cached_section(
            symbol=normalized_symbol,
            section="intraday",
            variant=variant,
            response=response,
        )
        return response

    async def _validate_symbol(self, symbol: str) -> str:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stock symbol not found",
            )
        if not await self.repository.exists_by_symbol(normalized_symbol):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stock symbol not found",
            )
        return normalized_symbol

    async def _get_cached_section(
        self,
        *,
        symbol: str,
        section: str,
        variant: str,
        response_model: type[BaseModel],
    ) -> BaseModel | None:
        try:
            cached = await self.cache.get_response(
                symbol=symbol,
                section=section,
                variant=variant,
                response_model=response_model,
            )
        except Exception as exc:
            logger.warning("Stock price cache read failed: %s", exc)
            return None
        if cached is None:
            return None
        return cached.model_copy(update={"cache_hit": True})

    async def _set_cached_section(
        self,
        *,
        symbol: str,
        section: str,
        variant: str,
        response: BaseModel,
    ) -> None:
        try:
            await self.cache.set_response(
                symbol=symbol,
                section=section,
                variant=variant,
                response=response,
            )
        except Exception as exc:
            logger.warning("Stock price cache write failed: %s", exc)

    @staticmethod
    def _validate_intraday_source_contract(query: StockPriceIntradayQuery) -> None:
        if query.source != "KBS":
            return
        if query.last_time is None and query.last_time_format is None:
            return
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="KBS intraday does not support last_time or last_time_format",
        )

    @staticmethod
    def _build_history_variant(query: StockPriceHistoryQuery) -> str:
        return ":".join(
            (
                f"source={StockPriceService._quote_variant_part(query.source)}",
                f"interval={StockPriceService._quote_variant_part(query.interval)}",
                f"start={StockPriceService._quote_variant_part(query.start)}",
                f"end={StockPriceService._quote_variant_part(query.end)}",
                f"length={StockPriceService._quote_variant_part(query.length)}",
            )
        )

    @staticmethod
    def _build_intraday_variant(query: StockPriceIntradayQuery) -> str:
        return ":".join(
            (
                f"source={StockPriceService._quote_variant_part(query.source)}",
                f"page_size={query.page_size}",
                f"last_time={StockPriceService._quote_variant_part(query.last_time)}",
                f"last_time_format={StockPriceService._quote_variant_part(query.last_time_format)}",
            )
        )

    @staticmethod
    def _quote_variant_part(value: Any) -> str:
        normalized = "" if value is None else str(value)
        return quote(normalized, safe="")

    @staticmethod
    def _map_fetch_error(exc: Exception) -> HTTPException:
        if isinstance(exc, HTTPException):
            return exc
        if StockPriceService._is_user_input_error(exc):
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
        logger.warning("Stock price upstream fetch failed: %s", exc)
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch stock price data from upstream provider",
        )

    @staticmethod
    def _is_user_input_error(exc: Exception) -> bool:
        if not isinstance(exc, ValueError):
            return False
        message = str(exc).strip().lower()
        if not message:
            return False
        return any(snippet in message for snippet in _USER_INPUT_ERROR_SNIPPETS)
