"""Company profile tool for the fundamental analyst runtime."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from app.agents.implementations.fundamental_analyst.tools.dependencies import (
    get_stock_company_service,
)
from app.agents.implementations.fundamental_analyst.tools.evidence import (
    normalize_symbol_for_tool,
)
from app.agents.implementations.fundamental_analyst.tools.schemas import (
    LoadCompanyProfileInput,
)
from app.services.stocks.company_service import StockCompanyService


async def load_company_profile_result(
    request: LoadCompanyProfileInput | dict[str, Any],
    *,
    stock_company_service: StockCompanyService | None = None,
) -> dict[str, Any]:
    """Load VCI company overview through the shared service."""
    normalized_request = LoadCompanyProfileInput.model_validate(request)
    try:
        symbol = normalize_symbol_for_tool(normalized_request.symbol)
        service = stock_company_service or get_stock_company_service()
        response = await service.get_overview(symbol)
    except Exception as exc:
        return {
            "symbol": _safe_symbol(normalized_request.symbol),
            "source": "VCI",
            "item": None,
            "data_gaps": [_exception_detail(exc)],
        }

    return {
        "symbol": response.symbol,
        "source": response.source,
        "item": response.item.model_dump(mode="json"),
        "data_gaps": [],
    }


async def _load_company_profile_tool(**kwargs: Any) -> dict[str, Any]:
    return await load_company_profile_result(kwargs)


def _safe_symbol(value: str) -> str | None:
    try:
        return normalize_symbol_for_tool(value)
    except Exception:
        return None


def _exception_detail(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail:
        return str(detail)
    message = str(exc).strip()
    return message or "Company overview unavailable."


load_company_profile = StructuredTool.from_function(
    coroutine=_load_company_profile_tool,
    name="load_company_profile",
    description=(
        "Load VCI company overview through StockCompanyService."
    ),
    args_schema=LoadCompanyProfileInput,
)
