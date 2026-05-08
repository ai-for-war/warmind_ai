from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agents.implementations.technical_analyst.validation import (
    TechnicalAnalystOutput,
    parse_technical_analyst_output,
)


def _assessment(state: str = "constructive") -> dict[str, object]:
    return {
        "state": state,
        "direction": "bullish",
        "confidence": "medium",
        "evidence": ["Computed indicator evidence supports this state."],
    }


def _technical_read_payload() -> dict[str, object]:
    return {
        "mode": "technical_read",
        "summary": "FPT technical evidence is constructive but not fully confirmed.",
        "symbol": "fpt",
        "interval": "1D",
        "confidence": "medium",
        "trend": _assessment("uptrend"),
        "momentum": _assessment("positive momentum"),
        "volatility": _assessment("normal volatility"),
        "volume_confirmation": _assessment("volume confirms recent move"),
        "support_levels": [
            {
                "label": "20_bar_low",
                "price": 100,
                "rationale": "Recent swing low.",
            }
        ],
        "resistance_levels": [
            {
                "label": "20_bar_high",
                "price": 120,
                "rationale": "Recent swing high.",
            }
        ],
        "signals": [
            {
                "name": "price_above_sma20",
                "direction": "bullish",
                "strength": "moderate",
                "evidence": ["Close is above SMA20."],
            }
        ],
        "risks": [
            {
                "title": "Nearby resistance",
                "description": "Price is close to a resistance zone.",
                "severity": "moderate",
            }
        ],
        "uncertainties": [{"description": "No backtest was requested."}],
        "indicator_snapshot": {
            "symbol": "FPT",
            "interval": "1D",
            "source": "VCI",
            "bars_loaded": 260,
            "as_of": "2025-12-31",
            "indicator_set": "core",
            "trend": [{"name": "sma_20", "value": 110.5, "signal": "bullish"}],
            "momentum": [{"name": "rsi_14", "value": 58.2, "signal": "bullish"}],
            "volatility": [],
            "volume": [],
            "support_levels": [],
            "resistance_levels": [],
            "unavailable_indicators": [],
        },
    }


def _trading_plan_payload() -> dict[str, object]:
    payload = _technical_read_payload()
    payload["mode"] = "trading_plan"
    payload["trading_plan"] = {
        "entry_zone": {
            "label": "pullback_zone",
            "lower_price": 105,
            "upper_price": 108,
            "rationale": "Pullback toward support.",
        },
        "stop_loss": {
            "label": "support_break",
            "price": 99,
            "rationale": "Break below recent support.",
        },
        "target_1": {
            "label": "recent_high",
            "price": 118,
            "rationale": "Retest recent resistance.",
        },
        "target_2": {
            "label": "extension",
            "price": 125,
            "rationale": "Measured move extension.",
        },
        "risk_reward": [
            {
                "target_label": "target_1",
                "entry_price": 106,
                "stop_loss": 99,
                "target_price": 118,
                "ratio": 1.71,
            }
        ],
        "invalidated_if": "Daily close below 99.",
        "rationale": "Plan is based on support hold and trend continuation.",
    }
    payload["backtest_summary"] = {
        "template_id": "sma_crossover",
        "timeframe": "1D",
        "date_from": "2025-01-01",
        "date_to": "2025-12-31",
        "total_return_pct": 12.0,
        "max_drawdown_pct": -6.2,
        "win_rate_pct": 66.7,
        "total_trades": 3,
        "profit_factor": 1.8,
        "notes": ["Historical evidence only."],
    }
    return payload


def test_technical_read_output_accepts_valid_payload() -> None:
    output = parse_technical_analyst_output(_technical_read_payload())

    assert output.mode == "technical_read"
    assert output.symbol == "FPT"
    assert output.interval == "1D"
    assert output.trading_plan is None
    assert output.indicator_snapshot is not None
    assert output.indicator_snapshot.bars_loaded == 260


def test_technical_read_output_accepts_json_string_payload() -> None:
    output = parse_technical_analyst_output(json.dumps(_technical_read_payload()))

    assert output.mode == "technical_read"
    assert output.support_levels[0].label == "20_bar_low"


def test_trading_plan_output_requires_trading_plan() -> None:
    payload = _technical_read_payload()
    payload["mode"] = "trading_plan"

    with pytest.raises(ValidationError) as exc_info:
        parse_technical_analyst_output(payload)

    assert "trading_plan output requires trading_plan" in str(exc_info.value)


def test_technical_read_rejects_unsolicited_trading_plan() -> None:
    payload = _trading_plan_payload()
    payload["mode"] = "technical_read"

    with pytest.raises(ValidationError) as exc_info:
        parse_technical_analyst_output(payload)

    assert "technical_read output must not include trading_plan" in str(exc_info.value)


def test_trading_plan_output_accepts_valid_payload() -> None:
    output = parse_technical_analyst_output(_trading_plan_payload())

    assert output.mode == "trading_plan"
    assert output.trading_plan is not None
    assert output.trading_plan.invalidated_if == "Daily close below 99."
    assert output.backtest_summary is not None
    assert output.backtest_summary.template_id == "sma_crossover"


def test_technical_analyst_output_schema_documents_field_meanings() -> None:
    schema = TechnicalAnalystOutput.model_json_schema()

    assert schema["properties"]["mode"]["description"]
    assert schema["properties"]["summary"]["description"]
    assert schema["properties"]["indicator_snapshot"]["description"]
    assert schema["properties"]["trading_plan"]["description"]
    assert schema["properties"]["backtest_summary"]["description"]
