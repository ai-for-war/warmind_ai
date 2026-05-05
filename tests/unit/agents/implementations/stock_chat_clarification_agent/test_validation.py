from __future__ import annotations

import pytest

from app.agents.implementations.stock_chat_clarification_agent.validation import (
    parse_stock_chat_clarification_result,
)


def _valid_option(option_id: str) -> dict[str, str]:
    return {
        "id": option_id,
        "label": "A specific stock ticker",
        "description": "I want to ask about a specific stock ticker.",
    }


def test_stock_chat_clarification_rejects_option_value_patch() -> None:
    payload = {
        "status": "clarification_required",
        "clarification": [
            {
                "question": "Which time horizon should I use?",
                "options": [
                    {
                        "id": "short_term",
                        "label": "Short term",
                        "description": "A few days to a few weeks.",
                        "value": {"time_horizon": "short_term"},
                    },
                    _valid_option("medium_term"),
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        parse_stock_chat_clarification_result(payload)


@pytest.mark.parametrize(
    "description",
    [
        "Mã cổ phiếu tôi muốn hỏi là ___.",
        "Công ty tôi muốn hỏi là ...",
        "I want to ask about [ticker].",
        "I want to ask about <company>.",
        "I want to ask about {symbol}.",
    ],
)
def test_stock_chat_clarification_rejects_fill_in_option_templates(
    description: str,
) -> None:
    payload = {
        "status": "clarification_required",
        "clarification": [
            {
                "question": "Bạn đang hỏi về mã cổ phiếu hoặc công ty nào?",
                "options": [
                    {
                        "id": "ticker_only",
                        "label": "Một mã cổ phiếu cụ thể",
                        "description": description,
                    },
                    {
                        "id": "company_only",
                        "label": "Một công ty cụ thể",
                        "description": "Tôi muốn hỏi về một công ty cụ thể.",
                    },
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match="fill-in placeholders"):
        parse_stock_chat_clarification_result(payload)


@pytest.mark.parametrize(
    ("label", "description"),
    [
        ("Nhập mã cổ phiếu", "Tôi muốn hỏi về một mã cổ phiếu cụ thể."),
        ("Một mã cổ phiếu cụ thể", "Tôi sẽ nhập mã cổ phiếu ở tin nhắn tiếp theo."),
        ("Type ticker", "I want to ask about a specific stock ticker."),
    ],
)
def test_stock_chat_clarification_rejects_text_entry_instruction_options(
    label: str,
    description: str,
) -> None:
    payload = {
        "status": "clarification_required",
        "clarification": [
            {
                "question": "Bạn đang hỏi về mã cổ phiếu hoặc công ty nào?",
                "options": [
                    {
                        "id": "ticker_only",
                        "label": label,
                        "description": description,
                    },
                    {
                        "id": "company_only",
                        "label": "Một công ty cụ thể",
                        "description": "Tôi muốn hỏi về một công ty cụ thể.",
                    },
                ],
            }
        ],
    }

    with pytest.raises(ValueError, match="text-entry instruction"):
        parse_stock_chat_clarification_result(payload)


def test_stock_chat_clarification_accepts_directly_selectable_options() -> None:
    payload = {
        "status": "clarification_required",
        "clarification": [
            {
                "question": "Bạn đang hỏi về mã cổ phiếu hoặc công ty nào?",
                "options": [
                    {
                        "id": "specific_ticker",
                        "label": "Một mã cổ phiếu cụ thể",
                        "description": "Tôi muốn hỏi về một mã cổ phiếu cụ thể.",
                    },
                    {
                        "id": "specific_company",
                        "label": "Một công ty cụ thể",
                        "description": "Tôi muốn hỏi về một công ty cụ thể.",
                    },
                ],
            }
        ],
    }

    result = parse_stock_chat_clarification_result(payload)

    assert result.status == "clarification_required"
    assert result.clarification is not None
    assert result.clarification[0].options[0].description == (
        "Tôi muốn hỏi về một mã cổ phiếu cụ thể."
    )
