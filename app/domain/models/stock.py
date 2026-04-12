"""Durable stock catalog persistence models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StockSymbol(BaseModel):
    """One normalized stock symbol document stored in MongoDB."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    id: str | None = Field(default=None, alias="_id")
    symbol: str
    normalized_symbol: str | None = None
    organ_name: str | None = None
    normalized_organ_name: str | None = None
    exchange: str | None = None
    groups: list[str] = Field(default_factory=list)
    industry_code: int | None = None
    industry_name: str | None = None
    source: str = "VCI"
    snapshot_at: datetime
    updated_at: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist the stock symbol in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("organ_name", "industry_name", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Collapse blank text fields to null for stable persistence."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("text fields must be strings")
        normalized = value.strip()
        return normalized or None

    @field_validator("exchange", "source", mode="before")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        """Store exchange and source values in uppercase form when present."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("exchange/source fields must be strings")
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("industry_code", mode="before")
    @classmethod
    def normalize_industry_code(cls, value: int | str | None) -> int | None:
        """Allow numeric industry codes to arrive as strings."""
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            return int(normalized)
        raise TypeError("industry_code must be an int, str, or None")

    @field_validator("groups", mode="before")
    @classmethod
    def normalize_groups(cls, value: list[str] | tuple[str, ...] | None) -> list[str]:
        """Persist deduplicated uppercase group identifiers."""
        if value is None:
            return []
        if isinstance(value, (str, bytes)):
            raise TypeError("groups must be a list of strings")

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise TypeError("groups must contain only strings")
            cleaned = item.strip().upper()
            if not cleaned or cleaned in seen:
                continue
            normalized.append(cleaned)
            seen.add(cleaned)
        return normalized

    @model_validator(mode="after")
    def populate_derived_fields(self) -> "StockSymbol":
        """Backfill stable derived fields for normalized querying."""
        self.id = self.id or self.symbol
        self.normalized_symbol = (self.normalized_symbol or self.symbol).strip().lower()
        if self.organ_name is None:
            self.normalized_organ_name = None
        else:
            self.normalized_organ_name = (
                self.normalized_organ_name or self.organ_name
            ).strip().lower() or None
        self.source = self.source or "VCI"
        return self
