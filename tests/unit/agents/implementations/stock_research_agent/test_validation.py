from __future__ import annotations

import pytest

from app.agents.implementations.stock_research_agent.validation import (
    StockResearchAgentOutput,
    parse_stock_research_output,
)


def test_parse_stock_research_output_accepts_markdown_report_with_sources_section() -> None:
    payload = """
<think>
internal reasoning
</think>

I now have enough information.

**Stock Research Report: FPT**

## Current Price Snapshot

Current price is around 95,800 VND.

## Thesis

FPT remains resilient [S1].

## Sources

- [S1] Example Source (https://example.com/fpt)
""".strip()

    output = parse_stock_research_output(payload)

    assert isinstance(output, StockResearchAgentOutput)
    assert output.content.startswith("**Stock Research Report: FPT**")
    assert "Current price is around 95,800 VND." in output.content
    assert len(output.sources) == 1
    assert output.sources[0].source_id == "S1"
    assert output.sources[0].url == "https://example.com/fpt"
    assert output.sources[0].title == "Example Source"


def test_parse_stock_research_output_rejects_markdown_when_citations_do_not_map() -> None:
    payload = """
## Thesis

FPT remains resilient [S2].

## Sources

- [S1] Example Source (https://example.com/fpt)
""".strip()

    with pytest.raises(ValueError, match="missing source_id values: S2"):
        parse_stock_research_output(payload)
