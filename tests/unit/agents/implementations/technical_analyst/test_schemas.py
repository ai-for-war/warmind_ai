from __future__ import annotations

from pydantic import ValidationError

from app.domain.schemas.backtest import SmaCrossoverTemplateParams
from app.domain.schemas.technical_analysis import (
    ComputeTechnicalIndicatorsInput,
    LoadPriceHistoryInput,
    RunTechnicalBacktestInput,
    TechnicalIndicatorConfig,
)


def test_compute_indicators_input_accepts_length_history_query() -> None:
    payload = ComputeTechnicalIndicatorsInput.model_validate(
        {
            "symbol": " fpt ",
            "length": 260,
            "indicator_set": "CORE",
        }
    )

    assert payload.symbol == "FPT"
    assert payload.interval == "1D"
    assert payload.indicator_set == "core"
    history_query = payload.to_stock_price_history_query()
    assert history_query.length == 260
    assert history_query.start is None


def test_compute_indicators_input_accepts_start_end_history_query() -> None:
    payload = ComputeTechnicalIndicatorsInput.model_validate(
        {
            "symbol": "HPG",
            "start": "2025-01-01",
            "end": "2025-12-31",
            "indicator_set": "trend",
        }
    )

    history_query = payload.to_stock_price_history_query()
    assert history_query.start == "2025-01-01"
    assert history_query.end == "2025-12-31"
    assert history_query.length is None


def test_compute_indicators_input_requires_exactly_one_history_mode() -> None:
    for payload in (
        {"symbol": "FPT", "indicator_set": "core"},
        {"symbol": "FPT", "length": 260, "start": "2025-01-01"},
    ):
        try:
            ComputeTechnicalIndicatorsInput.model_validate(payload)
        except ValidationError as exc:
            assert "provide exactly one of 'start' or 'length'" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("Expected invalid history mode to be rejected")


def test_compute_indicators_input_accepts_custom_config() -> None:
    payload = ComputeTechnicalIndicatorsInput.model_validate(
        {
            "symbol": "FPT",
            "length": 120,
            "indicator_set": "custom",
            "config": {
                "sma_windows": [20, 50, 20],
                "ema_windows": [10],
                "rsi_windows": [14],
                "macd": {
                    "fast_window": 12,
                    "slow_window": 26,
                    "signal_window": 9,
                },
                "bollinger": {"window": 20, "window_dev": 2},
                "atr_window": 14,
                "adx_window": 14,
                "volume_average_windows": [20],
                "include_obv": True,
                "include_support_resistance": True,
            },
        }
    )

    assert payload.config is not None
    assert payload.config.sma_windows == [20, 50]
    assert payload.config.include_obv is True


def test_compute_indicators_input_rejects_custom_without_config() -> None:
    try:
        ComputeTechnicalIndicatorsInput.model_validate(
            {"symbol": "FPT", "length": 120, "indicator_set": "custom"}
        )
    except ValidationError as exc:
        assert "config is required when indicator_set is custom" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected missing custom config to be rejected")


def test_load_price_history_input_uses_same_history_query_shape() -> None:
    payload = LoadPriceHistoryInput.model_validate(
        {"symbol": "fpt", "start": "2025-01-01", "end": "2025-02-01"}
    )

    assert payload.symbol == "FPT"
    assert payload.to_stock_price_history_query().start == "2025-01-01"


def test_run_backtest_input_documents_and_validates_template_params() -> None:
    payload = RunTechnicalBacktestInput.model_validate(
        {
            "symbol": "fpt",
            "date_from": "2025-01-01",
            "date_to": "2025-12-31",
            "template_id": "sma_crossover",
            "template_params": {"fast_window": 20, "slow_window": 50},
        }
    )

    assert payload.symbol == "FPT"
    assert isinstance(payload.template_params, SmaCrossoverTemplateParams)
    assert payload.to_backtest_run_request().template_id == "sma_crossover"


def test_run_backtest_input_rejects_template_param_mismatch() -> None:
    try:
        RunTechnicalBacktestInput.model_validate(
            {
                "symbol": "FPT",
                "date_from": "2025-01-01",
                "date_to": "2025-12-31",
                "template_id": "sma_crossover",
            }
        )
    except ValidationError as exc:
        assert "sma_crossover requires template_params" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected SMA crossover params to be required")


def test_custom_indicator_config_rejects_empty_request() -> None:
    try:
        TechnicalIndicatorConfig.model_validate({})
    except ValidationError as exc:
        assert "must request at least one indicator" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected empty custom config to be rejected")
