"""Tool surface builder for the technical analyst runtime."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from app.agents.implementations.technical_analyst.tools.backtest import run_backtest
from app.agents.implementations.technical_analyst.tools.compute_indicators import (
    compute_technical_indicators,
)
from app.agents.implementations.technical_analyst.tools.price_history import (
    load_price_history,
)


@dataclass(frozen=True)
class TechnicalAnalystToolSurface:
    """Resolved deterministic tools used by the technical analyst runtime."""

    compute_technical_indicators: BaseTool
    load_price_history: BaseTool
    run_backtest: BaseTool
    tools: tuple[BaseTool, BaseTool, BaseTool]


def get_technical_analyst_tool_surface() -> TechnicalAnalystToolSurface:
    """Return the deterministic technical-analysis tool surface."""
    return TechnicalAnalystToolSurface(
        compute_technical_indicators=compute_technical_indicators,
        load_price_history=load_price_history,
        run_backtest=run_backtest,
        tools=(compute_technical_indicators, load_price_history, run_backtest),
    )
