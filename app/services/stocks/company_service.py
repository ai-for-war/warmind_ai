"""Service layer for stock company information reads."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Callable

from fastapi import HTTPException, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.domain.schemas.stock_company import (
    StockCompanyAffiliateResponse,
    StockCompanyEventsResponse,
    StockCompanyNewsResponse,
    StockCompanyOfficersResponse,
    StockCompanyOverviewResponse,
    StockCompanyRatioSummaryResponse,
    StockCompanyReportsResponse,
    StockCompanyShareholdersResponse,
    StockCompanySubsidiariesResponse,
    StockCompanyTradingStatsResponse,
)
from app.repo.stock_symbol_repo import StockSymbolRepository
from app.services.stocks.company_cache import StockCompanyCache
from app.services.stocks.company_gateway import VnstockCompanyGateway

logger = logging.getLogger(__name__)


class StockCompanyService:
    """Coordinate symbol validation, cache usage, and upstream company reads."""

    def __init__(
        self,
        repository: StockSymbolRepository,
        gateway: VnstockCompanyGateway,
        cache: StockCompanyCache,
    ) -> None:
        self.repository = repository
        self.gateway = gateway
        self.cache = cache

    async def get_overview(self, symbol: str) -> StockCompanyOverviewResponse:
        return await self._get_snapshot_section(
            symbol=symbol,
            section="overview",
            response_model=StockCompanyOverviewResponse,
            fetcher=self.gateway.fetch_overview,
        )

    async def get_shareholders(
        self,
        symbol: str,
    ) -> StockCompanyShareholdersResponse:
        return await self._get_list_section(
            symbol=symbol,
            section="shareholders",
            response_model=StockCompanyShareholdersResponse,
            fetcher=self.gateway.fetch_shareholders,
        )

    async def get_officers(
        self,
        symbol: str,
        *,
        filter_by: str = "working",
    ) -> StockCompanyOfficersResponse:
        return await self._get_list_section(
            symbol=symbol,
            section="officers",
            response_model=StockCompanyOfficersResponse,
            variant=f"filter={filter_by}",
            fetcher=lambda normalized_symbol: self.gateway.fetch_officers(
                normalized_symbol,
                filter_by=filter_by,
            ),
        )

    async def get_subsidiaries(
        self,
        symbol: str,
        *,
        filter_by: str = "all",
    ) -> StockCompanySubsidiariesResponse:
        return await self._get_list_section(
            symbol=symbol,
            section="subsidiaries",
            response_model=StockCompanySubsidiariesResponse,
            variant=f"filter={filter_by}",
            fetcher=lambda normalized_symbol: self.gateway.fetch_subsidiaries(
                normalized_symbol,
                filter_by=filter_by,
            ),
        )

    async def get_affiliate(self, symbol: str) -> StockCompanyAffiliateResponse:
        return await self._get_list_section(
            symbol=symbol,
            section="affiliate",
            response_model=StockCompanyAffiliateResponse,
            fetcher=self.gateway.fetch_affiliate,
        )

    async def get_events(self, symbol: str) -> StockCompanyEventsResponse:
        return await self._get_list_section(
            symbol=symbol,
            section="events",
            response_model=StockCompanyEventsResponse,
            fetcher=self.gateway.fetch_events,
        )

    async def get_news(self, symbol: str) -> StockCompanyNewsResponse:
        return await self._get_list_section(
            symbol=symbol,
            section="news",
            response_model=StockCompanyNewsResponse,
            fetcher=self.gateway.fetch_news,
        )

    async def get_reports(self, symbol: str) -> StockCompanyReportsResponse:
        return await self._get_list_section(
            symbol=symbol,
            section="reports",
            response_model=StockCompanyReportsResponse,
            fetcher=self.gateway.fetch_reports,
        )

    async def get_ratio_summary(
        self,
        symbol: str,
    ) -> StockCompanyRatioSummaryResponse:
        return await self._get_snapshot_section(
            symbol=symbol,
            section="ratio-summary",
            response_model=StockCompanyRatioSummaryResponse,
            fetcher=self.gateway.fetch_ratio_summary,
        )

    async def get_trading_stats(
        self,
        symbol: str,
    ) -> StockCompanyTradingStatsResponse:
        return await self._get_snapshot_section(
            symbol=symbol,
            section="trading-stats",
            response_model=StockCompanyTradingStatsResponse,
            fetcher=self.gateway.fetch_trading_stats,
        )

    async def _get_snapshot_section(
        self,
        *,
        symbol: str,
        section: str,
        response_model: type[BaseModel],
        fetcher: Callable[[str], dict[str, Any]],
        variant: str | None = None,
    ) -> BaseModel:
        return await self._get_section(
            symbol=symbol,
            section=section,
            response_model=response_model,
            fetcher=fetcher,
            variant=variant,
            item_key="item",
        )

    async def _get_list_section(
        self,
        *,
        symbol: str,
        section: str,
        response_model: type[BaseModel],
        fetcher: Callable[[str], list[dict[str, Any]]],
        variant: str | None = None,
    ) -> BaseModel:
        return await self._get_section(
            symbol=symbol,
            section=section,
            response_model=response_model,
            fetcher=fetcher,
            variant=variant,
            item_key="items",
        )

    async def _get_section(
        self,
        *,
        symbol: str,
        section: str,
        response_model: type[BaseModel],
        fetcher: Callable[[str], Any],
        item_key: str,
        variant: str | None = None,
    ) -> BaseModel:
        normalized_symbol = await self._validate_symbol(symbol)

        cached = await self._get_cached_section(
            symbol=normalized_symbol,
            section=section,
            response_model=response_model,
            variant=variant,
        )
        if cached is not None:
            return cached

        try:
            payload = await run_in_threadpool(fetcher, normalized_symbol)
            response = response_model(
                symbol=normalized_symbol,
                source=self.gateway.SOURCE,
                fetched_at=datetime.now(timezone.utc),
                cache_hit=False,
                **{item_key: payload},
            )
        except Exception:
            stale = await self._get_cached_section(
                symbol=normalized_symbol,
                section=section,
                response_model=response_model,
                variant=variant,
            )
            if stale is not None:
                return stale
            raise

        await self._set_cached_section(
            symbol=normalized_symbol,
            section=section,
            response=response,
            variant=variant,
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
        response_model: type[BaseModel],
        variant: str | None,
    ) -> BaseModel | None:
        try:
            cached = await self.cache.get_response(
                symbol=symbol,
                section=section,
                response_model=response_model,
                variant=variant,
            )
        except Exception as exc:
            logger.warning("Stock company cache read failed: %s", exc)
            return None
        if cached is None:
            return None
        return cached.model_copy(update={"cache_hit": True})

    async def _set_cached_section(
        self,
        *,
        symbol: str,
        section: str,
        response: BaseModel,
        variant: str | None,
    ) -> None:
        try:
            await self.cache.set_response(
                symbol=symbol,
                section=section,
                response=response,
                variant=variant,
            )
        except Exception as exc:
            logger.warning("Stock company cache write failed: %s", exc)
