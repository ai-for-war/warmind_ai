"""Schemas for stock company information request and response payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.domain.schemas.stock import StockSchemaBase

StockCompanySource = Literal["VCI"]
OfficerFilter = Literal["working", "resigned", "all"]
SubsidiaryFilter = Literal["all", "subsidiary"]


class StockCompanyQueryBase(StockSchemaBase):
    """Base schema for stock company information query parameters."""


class StockCompanyOfficersQuery(StockCompanyQueryBase):
    """Query parameters for the company officers endpoint."""

    filter_by: OfficerFilter = "working"

    @field_validator("filter_by", mode="before")
    @classmethod
    def normalize_filter_by(cls, value: str | None) -> OfficerFilter:
        """Normalize officers filter text into the canonical runtime value."""
        if value is None:
            return "working"
        normalized = value.strip().lower()
        if not normalized:
            return "working"
        return normalized  # type: ignore[return-value]


class StockCompanySubsidiariesQuery(StockCompanyQueryBase):
    """Query parameters for the company subsidiaries endpoint."""

    filter_by: SubsidiaryFilter = "all"

    @field_validator("filter_by", mode="before")
    @classmethod
    def normalize_filter_by(cls, value: str | None) -> SubsidiaryFilter:
        """Normalize subsidiaries filter text into the canonical runtime value."""
        if value is None:
            return "all"
        normalized = value.strip().lower()
        if not normalized:
            return "all"
        return normalized  # type: ignore[return-value]


class StockCompanyResponseBase(StockSchemaBase):
    """Common response metadata for all stock company information sections."""

    symbol: str = Field(..., min_length=1)
    source: StockCompanySource = "VCI"
    fetched_at: datetime
    cache_hit: bool = False

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist response symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class StockCompanyOverviewItem(StockSchemaBase):
    """Canonical VCI overview fields for one company."""

    symbol: str = Field(..., min_length=1)
    id: int | None = None
    issue_share: int | float | None = None
    history: str | None = None
    company_profile: str | None = None
    icb_name2: str | None = None
    icb_name3: str | None = None
    icb_name4: str | None = None
    charter_capital: int | float | None = None
    financial_ratio_issue_share: int | float | None = None


class StockCompanyShareholderItem(StockSchemaBase):
    """One major shareholder row from VCI."""

    id: int | None = None
    share_holder: str | None = None
    quantity: int | float | None = None
    share_own_percent: int | float | None = None
    update_date: str | None = None


class StockCompanyOfficerItem(StockSchemaBase):
    """One officer row from VCI."""

    id: int | None = None
    officer_name: str | None = None
    officer_position: str | None = None
    position_short_name: str | None = None
    update_date: str | None = None
    officer_own_percent: int | float | None = None
    quantity: int | float | None = None
    type: str | None = None


class StockCompanySubsidiaryItem(StockSchemaBase):
    """One subsidiary row from VCI."""

    id: int | None = None
    sub_organ_code: str | None = None
    organ_name: str | None = None
    ownership_percent: int | float | None = None
    type: str | None = None


class StockCompanyAffiliateItem(StockSchemaBase):
    """One affiliate row from VCI."""

    id: int | None = None
    sub_organ_code: str | None = None
    organ_name: str | None = None
    ownership_percent: int | float | None = None


class StockCompanyEventItem(StockSchemaBase):
    """One company event row from VCI."""

    id: int | None = None
    event_title: str | None = None
    public_date: str | None = None
    issue_date: str | None = None
    source_url: str | None = None
    event_list_code: str | None = None
    ratio: int | float | None = None
    value: int | float | None = None
    record_date: str | None = None
    exright_date: str | None = None
    event_list_name: str | None = None


class StockCompanyNewsItem(StockSchemaBase):
    """One company news row from VCI."""

    id: int | None = None
    news_title: str | None = None
    news_sub_title: str | None = None
    friendly_sub_title: str | None = None
    news_image_url: str | None = None
    news_source_link: str | None = None
    created_at: str | None = None
    public_date: str | None = None
    updated_at: str | None = None
    lang_code: str | None = None
    news_id: int | None = None
    news_short_content: str | None = None
    news_full_content: str | None = None
    close_price: int | float | None = None
    ref_price: int | float | None = None
    floor: int | float | None = None
    ceiling: int | float | None = None
    price_change_pct: int | float | None = None


class StockCompanyReportItem(StockSchemaBase):
    """One company analysis report row from VCI."""

    date: str | None = None
    description: str | None = None
    link: str | None = None
    name: str | None = None


class StockCompanyRatioSummaryItem(StockSchemaBase):
    """Canonical VCI ratio-summary fields for one company snapshot."""

    symbol: str = Field(..., min_length=1)
    year_report: int | None = None
    length_report: int | None = None
    update_date: str | None = None
    revenue: int | float | None = None
    revenue_growth: int | float | None = None
    net_profit: int | float | None = None
    net_profit_growth: int | float | None = None
    roe: int | float | None = None
    roa: int | float | None = None
    pe: int | float | None = None
    pb: int | float | None = None
    eps: int | float | None = None
    issue_share: int | float | None = None
    charter_capital: int | float | None = None
    dividend: int | float | None = None
    de: int | float | None = None


class StockCompanyTradingStatsItem(StockSchemaBase):
    """Canonical VCI trading-stats fields for one company snapshot."""

    symbol: str = Field(..., min_length=1)
    exchange: str | None = None
    ev: int | float | None = None
    ceiling: int | float | None = None
    floor: int | float | None = None
    ref_price: int | float | None = None
    open: int | float | None = None
    match_price: int | float | None = None
    close_price: int | float | None = None
    price_change: int | float | None = None
    price_change_pct: int | float | None = None
    high: int | float | None = None
    low: int | float | None = None
    total_volume: int | float | None = None
    high_price_1y: int | float | None = None
    low_price_1y: int | float | None = None
    pct_low_change_1y: int | float | None = None
    pct_high_change_1y: int | float | None = None
    foreign_volume: int | float | None = None
    foreign_room: int | float | None = None
    avg_match_volume_2w: int | float | None = None
    foreign_holding_room: int | float | None = None
    current_holding_ratio: int | float | None = None
    max_holding_ratio: int | float | None = None


class StockCompanyOverviewResponse(StockCompanyResponseBase):
    """Response envelope for the overview section."""

    item: StockCompanyOverviewItem


class StockCompanyShareholdersResponse(StockCompanyResponseBase):
    """Response envelope for the shareholders section."""

    items: list[StockCompanyShareholderItem]


class StockCompanyOfficersResponse(StockCompanyResponseBase):
    """Response envelope for the officers section."""

    items: list[StockCompanyOfficerItem]


class StockCompanySubsidiariesResponse(StockCompanyResponseBase):
    """Response envelope for the subsidiaries section."""

    items: list[StockCompanySubsidiaryItem]


class StockCompanyAffiliateResponse(StockCompanyResponseBase):
    """Response envelope for the affiliate section."""

    items: list[StockCompanyAffiliateItem]


class StockCompanyEventsResponse(StockCompanyResponseBase):
    """Response envelope for the company events section."""

    items: list[StockCompanyEventItem]


class StockCompanyNewsResponse(StockCompanyResponseBase):
    """Response envelope for the company news section."""

    items: list[StockCompanyNewsItem]


class StockCompanyReportsResponse(StockCompanyResponseBase):
    """Response envelope for the company reports section."""

    items: list[StockCompanyReportItem]


class StockCompanyRatioSummaryResponse(StockCompanyResponseBase):
    """Response envelope for the ratio-summary section."""

    item: StockCompanyRatioSummaryItem


class StockCompanyTradingStatsResponse(StockCompanyResponseBase):
    """Response envelope for the trading-stats section."""

    item: StockCompanyTradingStatsItem
