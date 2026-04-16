"""Pure response builders for the public backtest API domain."""

from __future__ import annotations

from app.domain.schemas.backtest import BacktestRunRequest, BacktestRunResponse
from app.domain.schemas.backtest_api import (
    BacktestApiRunAssumptionsResponse,
    BacktestApiRunRequest,
    BacktestApiRunResponse,
    BacktestApiTemplateListResponse,
    BacktestApiTemplateParameterResponse,
    BacktestApiTemplateResponse,
)
from app.services.backtest.service import BacktestService

_DEFAULT_SMA_FAST_WINDOW = 20
_DEFAULT_SMA_SLOW_WINDOW = 50


def build_template_catalog(service: BacktestService) -> BacktestApiTemplateListResponse:
    """Build the FE-facing template catalog from the supported v1 registry scope."""
    items: list[BacktestApiTemplateResponse] = []

    for template_id in service.template_registry.supported_template_ids():
        items.append(_build_template_item(template_id))

    return BacktestApiTemplateListResponse(items=items)


def build_run_response(
    request: BacktestRunRequest | BacktestApiRunRequest,
    result: BacktestRunResponse,
) -> BacktestApiRunResponse:
    """Wrap one completed internal backtest result for the FE-facing API."""
    return BacktestApiRunResponse(
        result=result,
        assumptions=BacktestApiRunAssumptionsResponse.from_run_request(request),
    )


def _build_template_item(template_id: str) -> BacktestApiTemplateResponse:
    if template_id == "buy_and_hold":
        return BacktestApiTemplateResponse(
            template_id="buy_and_hold",
            display_name="Buy and Hold",
            description="Buy once at the first eligible entry and hold until the end of the backtest window.",
            parameters=[],
        )

    if template_id == "sma_crossover":
        return BacktestApiTemplateResponse(
            template_id="sma_crossover",
            display_name="SMA Crossover",
            description="Buy when the fast SMA crosses above the slow SMA and sell when it crosses below.",
            parameters=[
                BacktestApiTemplateParameterResponse(
                    name="fast_window",
                    type="integer",
                    required=True,
                    default=_DEFAULT_SMA_FAST_WINDOW,
                    min=1,
                    description="Number of daily bars used for the fast simple moving average.",
                ),
                BacktestApiTemplateParameterResponse(
                    name="slow_window",
                    type="integer",
                    required=True,
                    default=_DEFAULT_SMA_SLOW_WINDOW,
                    min=2,
                    description="Number of daily bars used for the slow simple moving average.",
                ),
            ],
        )

    raise ValueError(f"Unsupported public backtest template: {template_id}")
