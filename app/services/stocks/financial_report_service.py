"""Service layer for KBS stock financial report reads."""

from __future__ import annotations

import logging
import unicodedata
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.domain.schemas.stock_financial_report import (
    StockFinancialReportPeriod,
    StockFinancialReportQuery,
    StockFinancialReportResponse,
    StockFinancialReportType,
)
from app.repo.stock_symbol_repo import StockSymbolRepository
from app.services.stocks.financial_report_cache import StockFinancialReportCache
from app.services.stocks.financial_report_gateway import VnstockFinancialReportGateway

logger = logging.getLogger(__name__)

_NO_DATA_ERROR_SNIPPETS: tuple[str, ...] = (
    "khong tim thay du lieu",
    "khong tim thay bao cao",
    "no data",
)
_USER_INPUT_ERROR_SNIPPETS: tuple[str, ...] = (
    "unsupported financial report type",
    "unsupported financial report period",
    "ky bao cao tai chinh khong hop le",
)


class StockFinancialReportService:
    """Coordinate symbol validation, cache usage, and upstream KBS report reads."""

    def __init__(
        self,
        repository: StockSymbolRepository,
        gateway: VnstockFinancialReportGateway,
        cache: StockFinancialReportCache,
    ) -> None:
        self.repository = repository
        self.gateway = gateway
        self.cache = cache

    async def get_report(
        self,
        symbol: str,
        report_type: StockFinancialReportType | str,
        query: StockFinancialReportQuery,
    ) -> StockFinancialReportResponse:
        """Return one normalized KBS financial report for a stock symbol."""
        normalized_report_type = self._validate_report_type(report_type)
        normalized_query = self._validate_query(query)
        normalized_period = self._validate_period(normalized_query.period)
        normalized_symbol = await self._validate_symbol(symbol)

        cached = await self._get_cached_report(
            symbol=normalized_symbol,
            report_type=normalized_report_type,
            period=normalized_period,
        )
        if cached is not None:
            return cached

        try:
            payload = await run_in_threadpool(
                self.gateway.fetch_report,
                normalized_symbol,
                report_type=normalized_report_type,
                period=normalized_period,
            )
            response = StockFinancialReportResponse.model_validate(
                {
                    **payload,
                    "symbol": normalized_symbol,
                    "source": self.gateway.SOURCE,
                    "report_type": normalized_report_type,
                    "period": normalized_period,
                    "cache_hit": False,
                }
            )
        except Exception as exc:
            mapped = self._map_non_stale_fetch_error(exc)
            if mapped is not None:
                raise mapped from exc

            stale = await self._get_cached_report(
                symbol=normalized_symbol,
                report_type=normalized_report_type,
                period=normalized_period,
            )
            if stale is not None:
                return stale
            raise self._map_gateway_error(exc) from exc

        if not response.items:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Financial report data not found",
            )

        await self._set_cached_report(
            symbol=normalized_symbol,
            report_type=normalized_report_type,
            period=normalized_period,
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

    async def _get_cached_report(
        self,
        *,
        symbol: str,
        report_type: str,
        period: str,
    ) -> StockFinancialReportResponse | None:
        try:
            cached = await self.cache.get_response(
                symbol=symbol,
                report_type=report_type,
                period=period,
            )
        except Exception as exc:
            logger.warning("Stock financial report cache read failed: %s", exc)
            return None
        if cached is None:
            return None
        return cached.model_copy(update={"cache_hit": True})

    async def _set_cached_report(
        self,
        *,
        symbol: str,
        report_type: str,
        period: str,
        response: StockFinancialReportResponse,
    ) -> None:
        try:
            await self.cache.set_response(
                symbol=symbol,
                report_type=report_type,
                period=period,
                response=response,
            )
        except Exception as exc:
            logger.warning("Stock financial report cache write failed: %s", exc)

    @staticmethod
    def _validate_query(query: StockFinancialReportQuery) -> StockFinancialReportQuery:
        try:
            return StockFinancialReportQuery.model_validate(query)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    @staticmethod
    def _validate_report_type(report_type: StockFinancialReportType | str) -> str:
        try:
            if isinstance(report_type, StockFinancialReportType):
                return report_type.value
            if not isinstance(report_type, str):
                raise TypeError("report_type must be a string")
            return StockFinancialReportType(report_type.strip().lower()).value
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported financial report type",
            ) from exc

    @staticmethod
    def _validate_period(period: StockFinancialReportPeriod | str) -> str:
        try:
            if isinstance(period, StockFinancialReportPeriod):
                return period.value
            if not isinstance(period, str):
                raise TypeError("period must be a string")
            return StockFinancialReportPeriod(period.strip().lower()).value
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported financial report period",
            ) from exc

    @staticmethod
    def _map_non_stale_fetch_error(exc: Exception) -> HTTPException | None:
        if isinstance(exc, HTTPException):
            return exc
        if StockFinancialReportService._is_no_data_error(exc):
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Financial report data not found",
            )
        if StockFinancialReportService._is_user_input_error(exc):
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
        return None

    @staticmethod
    def _map_gateway_error(exc: Exception) -> HTTPException:
        logger.warning("Stock financial report upstream fetch failed: %s", exc)
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch stock financial report data from upstream provider",
        )

    @staticmethod
    def _is_no_data_error(exc: Exception) -> bool:
        if not isinstance(exc, ValueError):
            return False
        return StockFinancialReportService._message_contains(
            exc,
            _NO_DATA_ERROR_SNIPPETS,
        )

    @staticmethod
    def _is_user_input_error(exc: Exception) -> bool:
        if not isinstance(exc, (TypeError, ValueError)):
            return False
        return StockFinancialReportService._message_contains(
            exc,
            _USER_INPUT_ERROR_SNIPPETS,
        )

    @staticmethod
    def _message_contains(exc: Exception, snippets: tuple[str, ...]) -> bool:
        message = str(exc).strip().lower()
        if not message:
            return False
        candidates = {message, StockFinancialReportService._repair_mojibake(message)}
        normalized_candidates = {
            StockFinancialReportService._strip_accents(candidate)
            for candidate in candidates
        }
        return any(
            snippet in candidate
            for candidate in normalized_candidates
            for snippet in snippets
        )

    @staticmethod
    def _repair_mojibake(message: str) -> str:
        try:
            return message.encode("cp1252").decode("utf-8")
        except UnicodeError:
            return message

    @staticmethod
    def _strip_accents(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        return normalized.encode("ascii", "ignore").decode("ascii")
