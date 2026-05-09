from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agents.implementations.fundamental_analyst.validation import (
    FundamentalAnalystOutput,
    parse_fundamental_analyst_output,
)
from app.prompts.system.fundamental_analyst import (
    get_fundamental_analyst_system_prompt,
)


def _section(
    *,
    item: str = "Revenue",
    report_type: str | None = "income-statement",
    data_gaps: list[str] | None = None,
) -> dict[str, object]:
    evidence_rows: list[dict[str, object]] = []
    if data_gaps is None:
        evidence_rows.append(
            {
                "item": item,
                "report_type": report_type,
                "periods": ["Q1 2026"],
                "values": {"Q1 2026": 100},
            }
        )
    return {
        "assessment": f"{item} evidence is available.",
        "evidence_rows": evidence_rows,
        "interpretation": f"{item} supports the section assessment.",
        "risks": ["Evidence is limited to reported provider rows."],
        "data_gaps": data_gaps or [],
    }


def _fundamental_payload() -> dict[str, object]:
    return {
        "symbol": " fpt ",
        "period": "quarter",
        "summary": "Fundamental evidence is constructive but incomplete.",
        "confidence": "medium",
        "business_profile": _section(
            item="company_profile",
            report_type=None,
        ),
        "growth": _section(item="Revenue"),
        "profitability": _section(item="Net profit"),
        "financial_health": _section(
            item="Total liabilities",
            report_type="balance-sheet",
        ),
        "cash_flow_quality": _section(
            item="Operating cash flow",
            report_type="cash-flow",
        ),
        "valuation_ratios": _section(
            item="P/E",
            report_type="ratio",
        ),
        "bullish_fundamental_points": [
            "Reported revenue evidence is available.",
            "Reported revenue evidence is available.",
            " ",
        ],
        "bearish_fundamental_risks": ["Cash conversion needs confirmation."],
        "uncertainties": ["Provider row labels may vary by report."],
        "data_gaps": ["No deterministic peer benchmark was provided."],
    }


def test_fundamental_analyst_output_accepts_valid_payload() -> None:
    output = parse_fundamental_analyst_output(_fundamental_payload())

    assert output.symbol == "FPT"
    assert output.period == "quarter"
    assert output.confidence == "medium"
    assert output.growth.evidence_rows[0].item == "Revenue"
    assert output.growth.evidence_rows[0].report_type == "income-statement"
    assert output.bullish_fundamental_points == [
        "Reported revenue evidence is available."
    ]


def test_fundamental_analyst_output_accepts_fenced_json_payload() -> None:
    payload = json.dumps(_fundamental_payload())

    output = parse_fundamental_analyst_output(f"```json\n{payload}\n```")

    assert output.symbol == "FPT"
    assert output.valuation_ratios.evidence_rows[0].item == "P/E"


def test_fundamental_analyst_output_defaults_blank_period_to_quarter() -> None:
    payload = _fundamental_payload()
    payload["period"] = " "

    output = parse_fundamental_analyst_output(payload)

    assert output.period == "quarter"


def test_fundamental_analyst_output_rejects_invalid_payload() -> None:
    payload = _fundamental_payload()
    payload["period"] = "month"

    with pytest.raises(ValidationError):
        parse_fundamental_analyst_output(payload)


def test_fundamental_evidence_section_requires_evidence_or_gap() -> None:
    payload = _fundamental_payload()
    payload["growth"] = {
        "assessment": "Growth cannot be assessed.",
        "evidence_rows": [],
        "interpretation": "No relevant row was provided.",
        "risks": [],
        "data_gaps": [],
    }

    with pytest.raises(ValidationError) as exc_info:
        parse_fundamental_analyst_output(payload)

    assert "section requires evidence_rows or data_gaps" in str(exc_info.value)


def test_fundamental_output_rejects_technical_read_and_final_decision_fields() -> None:
    payload = _fundamental_payload()
    payload["mode"] = "technical_read"
    payload["final_recommendation"] = "buy"
    payload["target_price"] = 120_000

    with pytest.raises(ValidationError) as exc_info:
        parse_fundamental_analyst_output(payload)

    error_text = str(exc_info.value)
    assert "mode" in error_text
    assert "final_recommendation" in error_text
    assert "target_price" in error_text


def test_fundamental_prompt_prevents_final_recommendation_and_target_price_claims() -> None:
    prompt = get_fundamental_analyst_system_prompt()

    assert "Do not give buy/sell/hold/reduce/accumulate advice" in prompt
    assert "Do not produce intrinsic value, target price, DCF valuation" in prompt
    assert "Reported valuation ratios are evidence only" in prompt


def test_fundamental_analyst_output_schema_documents_field_meanings() -> None:
    schema = FundamentalAnalystOutput.model_json_schema()

    assert schema["properties"]["symbol"]["description"]
    assert schema["properties"]["period"]["description"]
    assert schema["properties"]["business_profile"]["description"]
    assert schema["properties"]["valuation_ratios"]["description"]
    assert schema["properties"]["data_gaps"]["description"]
