from __future__ import annotations

import math
from typing import Any

import pytest

from app.services.stocks.financial_report_gateway import (
    VnstockFinancialReportGateway,
)


class _FakeFrame:
    def __init__(
        self,
        records: list[dict[str, Any]],
        *,
        columns: list[str] | None = None,
        periods: list[str] | None = None,
    ) -> None:
        self._records = records
        self.columns = columns or list(records[0].keys() if records else [])
        self.attrs = {"periods": periods} if periods is not None else {}

    @property
    def empty(self) -> bool:
        return not self._records

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return list(self._records)


class _FakeFinance:
    def __init__(self, symbol: str, source: str, calls: list[tuple[str, str, str]]) -> None:
        self.symbol = symbol
        self.source = source
        self.calls = calls

    def income_statement(self, *, period: str) -> _FakeFrame:
        self.calls.append(("income_statement", self.symbol, period))
        return _report_frame()

    def balance_sheet(self, *, period: str) -> _FakeFrame:
        self.calls.append(("balance_sheet", self.symbol, period))
        return _report_frame()

    def cash_flow(self, *, period: str) -> _FakeFrame:
        self.calls.append(("cash_flow", self.symbol, period))
        return _report_frame()

    def ratio(self, *, period: str) -> _FakeFrame:
        self.calls.append(("ratio", self.symbol, period))
        return _report_frame()


def _report_frame() -> _FakeFrame:
    return _FakeFrame(
        [
            {
                "item": " Revenue ",
                "item_id": "revenue",
                "item_en": "Revenue",
                "unit": "VND",
                "levels": 1,
                "row_number": 1,
                "2025-Q4": math.nan,
                "2025-Q3": 100,
                "ignored": "not-a-period-when-attrs-exists",
            },
            {
                "item": " ",
                "item_id": "blank",
                "2025-Q4": 1,
                "2025-Q3": 2,
            },
        ],
        columns=[
            "item",
            "item_id",
            "item_en",
            "unit",
            "levels",
            "row_number",
            "2025-Q4",
            "2025-Q3",
        ],
        periods=["2025-Q4", "2025-Q3"],
    )


def _gateway_and_calls() -> tuple[
    VnstockFinancialReportGateway,
    list[tuple[str, str, str]],
]:
    calls: list[tuple[str, str, str]] = []

    def factory(symbol: str, source: str) -> _FakeFinance:
        return _FakeFinance(symbol, source, calls)

    return VnstockFinancialReportGateway(finance_factory=factory), calls


@pytest.mark.parametrize(
    ("report_type", "method_name"),
    [
        ("income-statement", "income_statement"),
        ("balance-sheet", "balance_sheet"),
        ("cash-flow", "cash_flow"),
        ("ratio", "ratio"),
    ],
)
def test_fetch_report_maps_public_type_to_kbs_method(
    report_type: str,
    method_name: str,
) -> None:
    gateway, calls = _gateway_and_calls()

    payload = gateway.fetch_report(" vci ", report_type=report_type, period=" Year ")

    assert payload["symbol"] == "VCI"
    assert payload["source"] == "KBS"
    assert payload["report_type"] == report_type
    assert payload["period"] == "year"
    assert calls == [(method_name, "VCI", "year")]


def test_fetch_report_converts_dataframe_to_ordered_rows_and_period_values() -> None:
    gateway, _ = _gateway_and_calls()

    payload = gateway.fetch_report("VCI", report_type="income-statement", period="quarter")

    assert payload["periods"] == ["2025-Q4", "2025-Q3"]
    assert payload["items"] == [
        {
            "item": "Revenue",
            "item_id": "revenue",
            "values": {"2025-Q4": None, "2025-Q3": 100},
        }
    ]


def test_extract_periods_falls_back_to_columns_when_attrs_are_missing() -> None:
    frame = _FakeFrame(
        [
            {
                "item": "ROE",
                "item_id": "roe",
                "item_en": "Return on Equity",
                "2025-Q4": 15.2,
                "2025-Q3": 14.8,
            }
        ],
        columns=["item", "item_id", "item_en", "2025-Q4", "2025-Q3"],
    )

    payload = VnstockFinancialReportGateway._to_report_payload(frame)  # noqa: SLF001

    assert payload["periods"] == ["2025-Q4", "2025-Q3"]
    assert payload["items"][0]["values"] == {"2025-Q4": 15.2, "2025-Q3": 14.8}


def test_to_report_payload_infers_periods_from_list_records() -> None:
    payload = VnstockFinancialReportGateway._to_report_payload(  # noqa: SLF001
        [
            {
                "item": "PE",
                "item_id": "pe",
                "2025-Q4": 12.5,
                "2025-Q3": 13.2,
            }
        ]
    )

    assert payload == {
        "periods": ["2025-Q4", "2025-Q3"],
        "items": [
            {
                "item": "PE",
                "item_id": "pe",
                "values": {"2025-Q4": 12.5, "2025-Q3": 13.2},
            }
        ],
    }


def test_empty_payloads_return_empty_items() -> None:
    payload = VnstockFinancialReportGateway._to_report_payload(  # noqa: SLF001
        _FakeFrame([], columns=["item", "item_id"])
    )

    assert payload == {"periods": [], "items": []}


def test_blank_symbol_is_rejected_before_building_finance() -> None:
    gateway, calls = _gateway_and_calls()

    with pytest.raises(ValueError, match="symbol must not be blank"):
        gateway.fetch_report(" ", report_type="income-statement", period="quarter")

    assert calls == []


def test_to_records_rejects_unsupported_payload_types() -> None:
    with pytest.raises(
        TypeError,
        match="Unsupported vnstock financial report payload type",
    ):
        VnstockFinancialReportGateway._to_records(object())  # noqa: SLF001
