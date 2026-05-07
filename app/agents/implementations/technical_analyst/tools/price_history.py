"""Raw price-history inspection tool for the technical analyst runtime."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from app.agents.implementations.technical_analyst.tools.dependencies import (
    get_stock_price_service,
)
from app.domain.schemas.technical_analysis import LoadPriceHistoryInput
from app.services.stocks.price_service import StockPriceService


async def load_price_history_result(
    request: LoadPriceHistoryInput | dict[str, Any],
    *,
    stock_price_service: StockPriceService | None = None,
) -> dict[str, Any]:
    """Load raw canonical OHLCV for optional candle inspection."""
    normalized_request = LoadPriceHistoryInput.model_validate(request)
    service = stock_price_service or get_stock_price_service()
    history = await service.get_history(
        normalized_request.symbol,
        normalized_request.to_stock_price_history_query(),
    )
    return {
        "symbol": history.symbol,
        "source": history.source,
        "interval": history.interval,
        "cache_hit": history.cache_hit,
        "bars_loaded": len(history.items),
        "items": [item.model_dump(mode="json") for item in history.items],
    }


async def _load_price_history_tool(**kwargs: Any) -> dict[str, Any]:
    return await load_price_history_result(kwargs)


load_price_history = StructuredTool.from_function(
    coroutine=_load_price_history_tool,
    name="load_price_history",
    description=(
        "Optional raw daily OHLCV inspection. Use this only when candle-level data "
        "inspection is needed; compute_technical_indicators loads its own history."
    ),
    args_schema=LoadPriceHistoryInput,
)
