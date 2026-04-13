from __future__ import annotations

from typing import Any

import pytest

from app.services.stocks.company_gateway import VnstockCompanyGateway


class _FakeFrame:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return list(self._records)


class _FakeCompany:
    def __init__(self, symbol: str, source: str, calls: list[tuple[str, str, dict[str, Any]]]) -> None:
        self.symbol = symbol
        self.source = source
        self.calls = calls

    def overview(self) -> _FakeFrame:
        self.calls.append(("overview", self.symbol, {}))
        return _FakeFrame(
            [
                {
                    "symbol": self.symbol,
                    "id": 7,
                    "issue_share": 123456,
                    "company_profile": "Cong ty Co phan FPT",
                    "history": "1988",
                    "icb_name2": "Technology",
                    "charter_capital": 1000,
                    "ignored": "drop-me",
                }
            ]
        )

    def shareholders(self) -> _FakeFrame:
        self.calls.append(("shareholders", self.symbol, {}))
        return _FakeFrame(
            [
                {
                    "id": 1,
                    "share_holder": "State Capital",
                    "quantity": 100,
                    "share_own_percent": 10.5,
                    "update_date": "2026-04-13",
                    "ignored": "drop-me",
                }
            ]
        )

    def officers(self, *, filter_by: str) -> _FakeFrame:
        self.calls.append(("officers", self.symbol, {"filter_by": filter_by}))
        return _FakeFrame(
            [
                {
                    "id": 1,
                    "officer_name": "A",
                    "officer_position": "CEO",
                    "position_short_name": "CEO",
                    "update_date": "2026-04-13",
                    "officer_own_percent": 1.2,
                    "quantity": 1000,
                    "type": "dang lam viec",
                    "ignored": "drop-me",
                }
            ]
        )

    def subsidiaries(self, *, filter_by: str) -> list[dict[str, Any]]:
        self.calls.append(("subsidiaries", self.symbol, {"filter_by": filter_by}))
        return [
            {
                "id": 2,
                "sub_organ_code": "SUB1",
                "organ_name": "FPT Software",
                "ownership_percent": 100,
                "type": "cong ty con",
                "ignored": "drop-me",
            }
        ]

    def affiliate(self) -> _FakeFrame:
        self.calls.append(("affiliate", self.symbol, {}))
        return _FakeFrame(
            [
                {
                    "id": 3,
                    "sub_organ_code": "AFF1",
                    "organ_name": "Affiliate 1",
                    "ownership_percent": 30,
                    "ignored": "drop-me",
                }
            ]
        )

    def events(self) -> _FakeFrame:
        self.calls.append(("events", self.symbol, {}))
        return _FakeFrame(
            [
                {
                    "id": 4,
                    "event_title": "Dividend",
                    "public_date": "2026-04-13",
                    "issue_date": "2026-04-14",
                    "source_url": "https://example.com",
                    "event_list_code": "DIV",
                    "ratio": 10,
                    "value": 1000,
                    "record_date": "2026-04-20",
                    "exright_date": "2026-04-18",
                    "event_list_name": "Tra co tuc",
                    "ignored": "drop-me",
                }
            ]
        )

    def news(self) -> _FakeFrame:
        self.calls.append(("news", self.symbol, {}))
        return _FakeFrame(
            [
                {
                    "id": 5,
                    "news_title": "FPT expands",
                    "news_short_content": "short",
                    "news_full_content": "full",
                    "public_date": 1775846542000,
                    "ignored": "drop-me",
                }
            ]
        )

    def reports(self) -> _FakeFrame:
        self.calls.append(("reports", self.symbol, {}))
        return _FakeFrame(
            [
                {
                    "date": "2026-04-13",
                    "description": "Analysis report",
                    "link": "https://example.com/report.pdf",
                    "name": "FPT report",
                    "ignored": "drop-me",
                }
            ]
        )

    def ratio_summary(self) -> _FakeFrame:
        self.calls.append(("ratio_summary", self.symbol, {}))
        return _FakeFrame(
            [
                {
                    "symbol": self.symbol,
                    "year_report": 2025,
                    "length_report": 4,
                    "update_date": 1774539195927,
                    "revenue": 100,
                    "roe": 10,
                    "ignored": "drop-me",
                }
            ]
        )

    def trading_stats(self) -> _FakeFrame:
        self.calls.append(("trading_stats", self.symbol, {}))
        return _FakeFrame(
            [
                {
                    "symbol": self.symbol,
                    "exchange": "HOSE",
                    "match_price": 100,
                    "close_price": 101,
                    "total_volume": 9999,
                    "ignored": "drop-me",
                }
            ]
        )


def _gateway_and_calls() -> tuple[VnstockCompanyGateway, list[tuple[str, str, dict[str, Any]]]]:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def factory(symbol: str, source: str) -> _FakeCompany:
        return _FakeCompany(symbol, source, calls)

    return VnstockCompanyGateway(company_factory=factory), calls


def test_fetch_overview_returns_only_canonical_vci_fields() -> None:
    gateway, calls = _gateway_and_calls()

    payload = gateway.fetch_overview(" fpt ")

    assert payload == {
        "symbol": "FPT",
        "id": 7,
        "issue_share": 123456,
        "company_profile": "Cong ty Co phan FPT",
        "history": "1988",
        "icb_name2": "Technology",
        "charter_capital": 1000,
    }
    assert calls == [("overview", "FPT", {})]


def test_fetch_officers_passes_filter_and_normalizes_record_fields() -> None:
    gateway, calls = _gateway_and_calls()

    payload = gateway.fetch_officers("fpt", filter_by="resigned")

    assert payload == [
        {
            "id": 1,
            "officer_name": "A",
            "officer_position": "CEO",
            "position_short_name": "CEO",
            "update_date": "2026-04-13",
            "officer_own_percent": 1.2,
            "quantity": 1000,
            "type": "dang lam viec",
        }
    ]
    assert calls == [("officers", "FPT", {"filter_by": "resigned"})]


def test_fetch_subsidiaries_supports_list_payloads() -> None:
    gateway, calls = _gateway_and_calls()

    payload = gateway.fetch_subsidiaries("fpt", filter_by="all")

    assert payload == [
        {
            "id": 2,
            "sub_organ_code": "SUB1",
            "organ_name": "FPT Software",
            "ownership_percent": 100,
            "type": "cong ty con",
        }
    ]
    assert calls == [("subsidiaries", "FPT", {"filter_by": "all"})]


def test_fetch_ratio_summary_returns_single_canonical_snapshot_record() -> None:
    gateway, calls = _gateway_and_calls()

    payload = gateway.fetch_ratio_summary("fpt")

    assert payload == {
        "symbol": "FPT",
        "year_report": 2025,
        "length_report": 4,
        "update_date": "2026-03-26T15:33:15Z",
        "revenue": 100,
        "roe": 10,
    }
    assert calls == [("ratio_summary", "FPT", {})]


def test_fetch_news_normalizes_runtime_timestamp_fields_to_strings() -> None:
    gateway, calls = _gateway_and_calls()

    payload = gateway.fetch_news("fpt")

    assert payload == [
        {
            "id": 5,
            "news_title": "FPT expands",
            "news_short_content": "short",
            "news_full_content": "full",
            "public_date": "2026-04-10T18:42:22Z",
        }
    ]
    assert calls == [("news", "FPT", {})]


def test_blank_symbol_is_rejected_before_building_company() -> None:
    gateway, _ = _gateway_and_calls()

    with pytest.raises(ValueError, match="symbol must not be blank"):
        gateway.fetch_news("   ")


def test_to_records_rejects_unsupported_payload_types() -> None:
    with pytest.raises(TypeError, match="Unsupported vnstock company payload type"):
        VnstockCompanyGateway._to_records(  # noqa: SLF001
            object(),
            allowed_fields=("id",),
        )
