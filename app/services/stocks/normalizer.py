"""Normalization helpers for turning vnstock listing payloads into stock models."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from app.domain.models.stock import StockSymbol

SYMBOL_KEYS: tuple[str, ...] = ("symbol",)
ORGANIZATION_NAME_KEYS: tuple[str, ...] = (
    "organ_name",
)
EXCHANGE_KEYS: tuple[str, ...] = ("exchange",)
INDUSTRY_CODE_KEYS: tuple[str, ...] = ("icb_code2",)
INDUSTRY_NAME_KEYS: tuple[str, ...] = ("icb_name2",)


def build_stock_symbol_snapshot(
    *,
    all_symbols: Iterable[dict[str, Any]],
    symbols_by_exchange: Iterable[dict[str, Any]],
    symbols_by_industries: Iterable[dict[str, Any]],
    group_memberships: dict[str, list[str]],
    source: str = "VCI",
    now: datetime | None = None,
) -> list[StockSymbol]:
    """Merge multiple vnstock listing views into one stock-symbol snapshot."""
    timestamp = now or datetime.now(timezone.utc)
    merged: dict[str, dict[str, Any]] = {}

    for record in all_symbols:
        _merge_record(merged, record)
    for record in symbols_by_exchange:
        _merge_record(merged, record)
    for record in symbols_by_industries:
        _merge_record(merged, record)

    for symbol, groups in group_memberships.items():
        entry = merged.setdefault(symbol, {"symbol": symbol})
        entry["groups"] = sorted(
            {
                *entry.get("groups", []),
                *(group_name.strip().upper() for group_name in groups if group_name),
            }
        )

    snapshot: list[StockSymbol] = []
    for symbol, payload in merged.items():
        payload["symbol"] = symbol
        payload.setdefault("groups", [])
        payload["source"] = source
        payload["snapshot_at"] = timestamp
        payload["updated_at"] = timestamp
        snapshot.append(StockSymbol(**payload))

    snapshot.sort(key=lambda item: item.symbol)
    return snapshot


def _merge_record(
    merged: dict[str, dict[str, Any]],
    record: dict[str, Any] | None,
) -> None:
    """Merge one raw vnstock record into the accumulating snapshot map."""
    if not isinstance(record, dict):
        return

    symbol = _extract_symbol(record)
    if symbol is None:
        return

    entry = merged.setdefault(symbol, {"symbol": symbol})

    organ_name = _first_non_blank(record, ORGANIZATION_NAME_KEYS)
    if organ_name is not None:
        entry["organ_name"] = organ_name

    exchange = _first_non_blank(record, EXCHANGE_KEYS)
    if exchange is not None:
        entry["exchange"] = str(exchange).strip().upper()

    industry_code = _first_non_blank(record, INDUSTRY_CODE_KEYS)
    if industry_code is not None:
        entry["industry_code"] = industry_code

    industry_name = _first_non_blank(record, INDUSTRY_NAME_KEYS)
    if industry_name is not None:
        entry["industry_name"] = industry_name


def _extract_symbol(record: dict[str, Any]) -> str | None:
    """Extract and normalize one stock symbol from a raw listing record."""
    raw_symbol = _first_non_blank(record, SYMBOL_KEYS)
    if raw_symbol is None:
        return None
    return str(raw_symbol).strip().upper() or None


def _first_non_blank(
    record: dict[str, Any],
    keys: Iterable[str],
) -> Any | None:
    """Return the first non-empty value across the supplied candidate keys."""
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
            continue
        return value
    return None
