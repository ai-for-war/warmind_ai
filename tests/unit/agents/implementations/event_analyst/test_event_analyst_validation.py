from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agents.implementations.event_analyst.validation import (
    EventAnalystOutput,
    parse_event_analyst_output,
)


def _valid_payload() -> dict[str, object]:
    return {
        "summary": "A policy catalyst may support FPT demand expectations [S1].",
        "events": [
            {
                "title": "Policy catalyst",
                "description": "A policy update may improve sector demand [S1].",
                "event_type": "policy",
                "event_date": "2026-05-07",
                "impact_direction": "bullish",
                "impact_horizon": "short_term",
                "source_ids": ["S1"],
            }
        ],
        "impact_direction": "bullish",
        "impact_confidence": "medium",
        "bullish_catalysts": ["Policy support [S1]"],
        "bearish_risks": [],
        "uncertainties": ["Need company confirmation"],
        "sources": [
            {
                "source_id": "S1",
                "url": "https://example.com/fpt",
                "title": "Example Source",
            }
        ],
    }


def test_event_analyst_output_accepts_valid_source_backed_payload() -> None:
    output = parse_event_analyst_output(_valid_payload())

    assert output.summary.startswith("A policy catalyst")
    assert output.impact_direction == "bullish"
    assert output.impact_confidence == "medium"
    assert output.events[0].source_ids == ["S1"]
    assert output.sources[0].source_id == "S1"


def test_event_analyst_output_accepts_json_string_payload() -> None:
    output = parse_event_analyst_output(json.dumps(_valid_payload()))

    assert output.sources[0].url == "https://example.com/fpt"


def test_event_analyst_output_rejects_missing_cited_source_id() -> None:
    payload = _valid_payload()
    payload["summary"] = "This cites a missing source [S2]."

    with pytest.raises(ValidationError) as exc_info:
        parse_event_analyst_output(payload)

    assert "missing source_id values: S2" in str(exc_info.value)


def test_event_analyst_output_rejects_event_source_id_without_source() -> None:
    payload = _valid_payload()
    events = payload["events"]
    assert isinstance(events, list)
    event = events[0]
    assert isinstance(event, dict)
    event["source_ids"] = ["S2"]

    with pytest.raises(ValidationError) as exc_info:
        parse_event_analyst_output(payload)

    assert "missing source_id values: S2" in str(exc_info.value)


def test_event_analyst_output_rejects_duplicate_source_ids() -> None:
    payload = _valid_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    sources.append(
        {
            "source_id": "S1",
            "url": "https://example.com/duplicate",
            "title": "Duplicate Source",
        }
    )

    with pytest.raises(ValidationError) as exc_info:
        parse_event_analyst_output(payload)

    assert "sources must use unique source_id values" in str(exc_info.value)


def test_event_analyst_output_schema_documents_field_meanings() -> None:
    schema = EventAnalystOutput.model_json_schema()

    assert schema["properties"]["summary"]["description"]
    assert schema["properties"]["impact_direction"]["description"]
    assert schema["properties"]["sources"]["description"]

    definitions = schema["$defs"]
    event_schema = definitions["EventAnalystEvent"]
    source_schema = definitions["EventAnalystOutputSource"]
    assert event_schema["properties"]["impact_horizon"]["description"]
    assert source_schema["properties"]["source_id"]["description"]
