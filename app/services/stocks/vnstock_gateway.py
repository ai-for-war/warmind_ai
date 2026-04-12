"""Upstream gateway for loading stock catalog data from vnstock VCI listings."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from vnstock import Listing, register_user

from app.config.settings import get_settings


SUPPORTED_STOCK_GROUPS: tuple[str, ...] = (
    "VN30",
    "VN100",
    "VNAllShare",
    "VNMidCap",
    "VNSmallCap",
    "HNX30",
    "ETF",
    "CW",
)


class VnstockListingGateway:
    """Thin wrapper around vnstock Listing(source='VCI')."""

    SOURCE = "VCI"

    def __init__(self) -> None:
        settings = get_settings()
        register_user(api_key=settings.VNSTOCK_API_KEY)
        self.listing = Listing(source=self.SOURCE)

    def fetch_all_symbols(self) -> list[dict[str, Any]]:
        """Fetch the base stock symbol listing from VCI."""
        dataframe = self.listing.all_symbols()
        return self._to_records(dataframe)

    def fetch_symbols_by_exchange(self) -> list[dict[str, Any]]:
        """Fetch detailed stock listings grouped by exchange."""
        dataframe = self.listing.symbols_by_exchange()
        return self._to_records(dataframe)

    def fetch_symbols_by_industries(self) -> list[dict[str, Any]]:
        """Fetch stock listing metadata grouped by industry."""
        dataframe = self.listing.symbols_by_industries()
        return self._to_records(dataframe)

    def fetch_group_memberships(
        self,
        groups: Iterable[str] | None = None,
    ) -> dict[str, list[str]]:
        """Fetch symbol membership for the configured stock groups."""
        memberships: dict[str, set[str]] = {}

        for group_name in groups or SUPPORTED_STOCK_GROUPS:
            # The installed vnstock runtime delegates with `group=...` even though
            # the public docs currently show `group_name=...`.
            symbols = self.listing.symbols_by_group(group=group_name)
            for raw_symbol in self._to_symbol_list(symbols):
                normalized_symbol = raw_symbol.strip().upper()
                if not normalized_symbol:
                    continue
                memberships.setdefault(normalized_symbol, set()).add(
                    group_name.strip().upper()
                )

        return {
            symbol: sorted(group_names)
            for symbol, group_names in memberships.items()
        }

    @staticmethod
    def _to_records(dataframe: Any) -> list[dict[str, Any]]:
        """Convert one vnstock DataFrame-like result to plain dictionaries."""
        if dataframe is None:
            return []
        if hasattr(dataframe, "to_dict"):
            return list(dataframe.to_dict(orient="records"))
        if isinstance(dataframe, list):
            return [item for item in dataframe if isinstance(item, dict)]
        raise TypeError("Unsupported vnstock listing payload type")

    @staticmethod
    def _to_symbol_list(payload: Any) -> list[str]:
        """Convert one vnstock group payload to a list of symbols."""
        if payload is None:
            return []
        if isinstance(payload, list):
            return [str(item) for item in payload]
        if hasattr(payload, "tolist"):
            return [str(item) for item in payload.tolist()]
        if hasattr(payload, "to_dict"):
            records = payload.to_dict(orient="records")
            symbols: list[str] = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                symbol = record.get("symbol")
                if symbol is not None:
                    symbols.append(str(symbol))
            return symbols
        raise TypeError("Unsupported vnstock group payload type")
