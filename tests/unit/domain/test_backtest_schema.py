from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.schemas.backtest import (
    BuyAndHoldTemplateParams,
    DEFAULT_BACKTEST_INITIAL_CAPITAL,
    SmaCrossoverTemplateParams,
    BacktestRunRequest,
)


def test_backtest_run_request_defaults_to_v1_scope() -> None:
    request = BacktestRunRequest(
        symbol=" fpt ",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 12, 31),
    )

    assert request.symbol == "FPT"
    assert request.timeframe == "1D"
    assert request.direction == "long_only"
    assert request.position_sizing == "all_in"
    assert request.execution_model == "next_open"
    assert request.template_id == "buy_and_hold"
    assert request.initial_capital == DEFAULT_BACKTEST_INITIAL_CAPITAL
    assert isinstance(request.template_params, BuyAndHoldTemplateParams)


def test_backtest_run_request_normalizes_literal_inputs() -> None:
    request = BacktestRunRequest(
        symbol="acb",
        timeframe="1d",
        direction=" LONG_ONLY ",
        position_sizing=" ALL_IN ",
        execution_model=" NEXT_OPEN ",
        template_id=" SMA_CROSSOVER ",
        template_params={"fast_window": 20, "slow_window": 50},
        date_from=date(2024, 1, 1),
        date_to=date(2024, 12, 31),
    )

    assert request.timeframe == "1D"
    assert request.direction == "long_only"
    assert request.position_sizing == "all_in"
    assert request.execution_model == "next_open"
    assert request.template_id == "sma_crossover"
    assert isinstance(request.template_params, SmaCrossoverTemplateParams)


def test_backtest_run_request_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError, match="date_to must be on or after date_from"):
        BacktestRunRequest(
            symbol="FPT",
            date_from=date(2024, 12, 31),
            date_to=date(2024, 1, 1),
        )


def test_buy_and_hold_rejects_unexpected_template_params() -> None:
    with pytest.raises(
        ValidationError,
        match="buy_and_hold does not accept template parameters",
    ):
        BacktestRunRequest(
            symbol="FPT",
            template_id="buy_and_hold",
            template_params={"fast_window": 20, "slow_window": 50},
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
        )


def test_sma_crossover_requires_strategy_params() -> None:
    with pytest.raises(
        ValidationError,
        match="sma_crossover requires template_params with fast_window and slow_window",
    ):
        BacktestRunRequest(
            symbol="FPT",
            template_id="sma_crossover",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
        )


def test_sma_crossover_template_params_reject_invalid_window_order() -> None:
    with pytest.raises(
        ValidationError,
        match="fast_window must be less than slow_window",
    ):
        SmaCrossoverTemplateParams(fast_window=50, slow_window=20)
