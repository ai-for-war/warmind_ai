from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any

import pytest

from app.services.stocks.price_gateway import VnstockPriceGateway


class _FakeFrame:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return list(self._records)


class _FakeQuote:
    def __init__(
        self, symbol: str, source: str, calls: list[tuple[str, str, dict[str, Any]]]
    ) -> None:
        self.symbol = symbol
        self.source = source
        self.calls = calls

    def history(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        interval: str = "1D",
        length: int | str | None = None,
    ) -> _FakeFrame:
        self.calls.append(
            (
                "history",
                self.symbol,
                {
                    "source": self.source,
                    "start": start,
                    "end": end,
                    "interval": interval,
                    "length": length,
                },
            )
        )
        return _FakeFrame(
            [
                {
                    "time": datetime(2026, 4, 15, 9, 15, 0),
                    "open": 101.5,
                    "high": 102.0,
                    "low": 100.1,
                    "close": 101.9,
                    "volume": 1000,
                    "ignored": "drop-me",
                }
            ]
        )

    def intraday(
        self,
        *,
        page_size: int = 100,
        last_time: str | None = None,
        last_time_format: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            (
                "intraday",
                self.symbol,
                {
                    "source": self.source,
                    "page_size": page_size,
                    "last_time": last_time,
                    "last_time_format": last_time_format,
                },
            )
        )
        return [
            {
                "time": date(2026, 4, 15),
                "price": 101.2,
                "volume": 50,
                "match_type": "Buy",
                "id": "42",
                "ignored": "drop-me",
            }
        ]


def _gateway_and_calls() -> tuple[
    VnstockPriceGateway, list[tuple[str, str, dict[str, Any]]]
]:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def factory(symbol: str, source: str) -> _FakeQuote:
        return _FakeQuote(symbol, source, calls)

    return VnstockPriceGateway(quote_factory=factory), calls


def test_fetch_history_returns_only_canonical_vci_fields() -> None:
    gateway, calls = _gateway_and_calls()

    payload = gateway.fetch_history(
        " fpt ",
        start="2026-04-01",
        end="2026-04-15",
        interval="1D",
    )

    assert payload == [
        {
            "time": "2026-04-15T09:15:00",
            "open": 101.5,
            "high": 102.0,
            "low": 100.1,
            "close": 101.9,
            "volume": 1000,
        }
    ]
    assert calls == [
        (
            "history",
            "FPT",
            {
                "source": "VCI",
                "start": "2026-04-01",
                "end": "2026-04-15",
                "interval": "1D",
                "length": None,
            },
        )
    ]


def test_fetch_intraday_passes_runtime_specific_cursor_parameters() -> None:
    gateway, calls = _gateway_and_calls()

    payload = gateway.fetch_intraday(
        "fpt",
        page_size=200,
        last_time="2026-04-15 09:15:00",
        last_time_format="%Y-%m-%d %H:%M:%S",
    )

    assert payload == [
        {
            "time": "2026-04-15",
            "price": 101.2,
            "volume": 50,
            "match_type": "Buy",
            "id": 42,
        }
    ]
    assert calls == [
        (
            "intraday",
            "FPT",
            {
                "source": "VCI",
                "page_size": 200,
                "last_time": "2026-04-15 09:15:00",
                "last_time_format": "%Y-%m-%d %H:%M:%S",
            },
        )
    ]


@pytest.mark.parametrize("method_name", ["history", "intraday"])
def test_fetch_price_methods_pass_explicit_kbs_source(method_name: str) -> None:
    gateway, calls = _gateway_and_calls()

    getattr(gateway, f"fetch_{method_name}")("fpt", source="KBS")

    assert calls[0][2]["source"] == "KBS"


@pytest.mark.parametrize("method_name", ["history", "intraday"])
def test_empty_payloads_return_empty_lists(method_name: str) -> None:
    class _EmptyQuote:
        def __init__(self, symbol: str, source: str) -> None:
            self.symbol = symbol
            self.source = source

        def history(self, **kwargs) -> _FakeFrame:
            del kwargs
            return _FakeFrame([])

        def intraday(self, **kwargs) -> list[dict[str, Any]]:
            del kwargs
            return []

    gateway = VnstockPriceGateway(
        quote_factory=lambda symbol, source: _EmptyQuote(symbol, source)
    )

    payload = getattr(gateway, f"fetch_{method_name}")("fpt")

    assert payload == []


def test_to_records_coerces_nan_cells_to_none() -> None:
    payload = VnstockPriceGateway._to_records(  # noqa: SLF001
        _FakeFrame(
            [
                {
                    "time": math.nan,
                    "open": math.nan,
                    "close": 101.1,
                }
            ]
        ),
        allowed_fields=("time", "open", "close"),
        transform_record=VnstockPriceGateway._normalize_history_record,  # noqa: SLF001
    )

    assert payload == [{"time": None, "open": None, "close": 101.1}]


def test_blank_symbol_is_rejected_before_building_quote() -> None:
    gateway, _ = _gateway_and_calls()

    with pytest.raises(ValueError, match="symbol must not be blank"):
        gateway.fetch_history("   ", length=30)


def test_to_records_rejects_unsupported_payload_types() -> None:
    with pytest.raises(TypeError, match="Unsupported vnstock price payload type"):
        VnstockPriceGateway._to_records(  # noqa: SLF001
            object(),
            allowed_fields=("time",),
        )
