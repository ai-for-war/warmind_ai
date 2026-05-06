"""Schemas for sandbox trade-agent request and response payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.domain.models.sandbox_trade_agent import (
    SandboxTradeAction,
    SandboxTradeOrderSide,
    SandboxTradeOrderStatus,
    SandboxTradeQuantityType,
    SandboxTradeSessionStatus,
    SandboxTradeSettlementAssetType,
    SandboxTradeSettlementStatus,
    SandboxTradeTickStatus,
)
from app.domain.schemas.stock import (
    DEFAULT_STOCK_PAGE_SIZE,
    MAX_STOCK_PAGE_SIZE,
    StockSchemaBase,
)
from app.domain.schemas.stock_research_report import MAX_STOCK_RESEARCH_SYMBOL_LENGTH

DEFAULT_SANDBOX_TRADE_INITIAL_CAPITAL = 100_000_000


class SandboxTradeAgentSchemaBase(StockSchemaBase):
    """Base schema for sandbox trade-agent transport payloads."""


class SandboxTradeAgentRuntimeConfigRequest(SandboxTradeAgentSchemaBase):
    """Requested runtime configuration for one sandbox trade-agent session."""

    provider: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=200)
    reasoning: str | None = Field(default=None, min_length=1, max_length=50)


class SandboxTradeAgentRuntimeConfigResponse(SandboxTradeAgentSchemaBase):
    """Resolved runtime configuration returned with one sandbox trade session."""

    provider: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=200)
    reasoning: str | None = Field(default=None, min_length=1, max_length=50)


class SandboxTradeSessionCreateRequest(SandboxTradeAgentSchemaBase):
    """Request payload for creating one sandbox trade-agent session."""

    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    initial_capital: float = Field(
        default=DEFAULT_SANDBOX_TRADE_INITIAL_CAPITAL,
        gt=0,
    )
    runtime_config: SandboxTradeAgentRuntimeConfigRequest | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize requested symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class SandboxTradeSessionUpdateRequest(SandboxTradeAgentSchemaBase):
    """Request payload for updating mutable sandbox trade-session fields."""

    runtime_config: SandboxTradeAgentRuntimeConfigRequest | None = None


class SandboxTradeSessionLifecycleResponse(SandboxTradeAgentSchemaBase):
    """Response returned after changing a sandbox trade-session lifecycle state."""

    id: str = Field(..., min_length=1)
    status: SandboxTradeSessionStatus
    updated_at: datetime


class SandboxTradeSessionSummary(SandboxTradeAgentSchemaBase):
    """Common sandbox trade-session fields returned by session APIs."""

    id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    status: SandboxTradeSessionStatus
    initial_capital: float = Field(..., gt=0)
    next_run_at: datetime
    last_tick_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    runtime_config: SandboxTradeAgentRuntimeConfigResponse | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize response symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class SandboxTradeSessionResponse(SandboxTradeSessionSummary):
    """Full response payload for one sandbox trade-agent session."""


class SandboxTradeSessionListResponse(SandboxTradeAgentSchemaBase):
    """Response returned by the sandbox trade-session list endpoint."""

    items: list[SandboxTradeSessionSummary] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default=DEFAULT_STOCK_PAGE_SIZE,
        ge=1,
        le=MAX_STOCK_PAGE_SIZE,
    )


class SandboxTradeSessionDeleteResponse(SandboxTradeAgentSchemaBase):
    """Response payload for successful sandbox trade-session deletion."""

    id: str = Field(..., min_length=1)
    deleted: bool = True


class SandboxTradeMarketSnapshotResponse(SandboxTradeAgentSchemaBase):
    """Market-data snapshot returned with a sandbox trade tick."""

    symbol: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    latest_price: float = Field(..., ge=0)
    observed_at: datetime | None = None
    summary: dict[str, object] = Field(default_factory=dict)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize market snapshot symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class SandboxTradeDecisionResponse(SandboxTradeAgentSchemaBase):
    """Structured autonomous decision returned by the sandbox trade agent."""

    action: SandboxTradeAction
    quantity_type: SandboxTradeQuantityType | None = None
    quantity_value: float | None = Field(default=None, gt=0)
    reason: str = Field(..., min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_notes: list[str] = Field(default_factory=list)


class SandboxTradeTickResponse(SandboxTradeAgentSchemaBase):
    """Response payload for one sandbox trade-agent tick."""

    id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tick_at: datetime
    status: SandboxTradeTickStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    market_snapshot: SandboxTradeMarketSnapshotResponse | None = None
    decision: SandboxTradeDecisionResponse | None = None
    order_id: str | None = Field(default=None, min_length=1)
    skip_reason: str | None = Field(default=None, min_length=1)
    rejection_reason: str | None = Field(default=None, min_length=1)
    error: str | None = Field(default=None, min_length=1)
    created_at: datetime
    updated_at: datetime


class SandboxTradeTickListResponse(SandboxTradeAgentSchemaBase):
    """Paginated tick history for one sandbox trade-agent session."""

    items: list[SandboxTradeTickResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default=DEFAULT_STOCK_PAGE_SIZE,
        ge=1,
        le=MAX_STOCK_PAGE_SIZE,
    )


class SandboxTradeOrderResponse(SandboxTradeAgentSchemaBase):
    """Response payload for one sandbox order."""

    id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tick_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    side: SandboxTradeOrderSide
    status: SandboxTradeOrderStatus
    quantity: float = Field(..., ge=0)
    price: float | None = Field(default=None, ge=0)
    gross_amount: float = Field(..., ge=0)
    rejection_reason: str | None = Field(default=None, min_length=1)
    filled_at: datetime | None = None
    trade_date: str | None = Field(default=None, min_length=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize order symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class SandboxTradeOrderListResponse(SandboxTradeAgentSchemaBase):
    """Paginated sandbox order history for one session."""

    items: list[SandboxTradeOrderResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default=DEFAULT_STOCK_PAGE_SIZE,
        ge=1,
        le=MAX_STOCK_PAGE_SIZE,
    )


class SandboxTradePositionResponse(SandboxTradeAgentSchemaBase):
    """Current single-symbol position state for one sandbox session."""

    session_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    available_cash: float = Field(..., ge=0)
    pending_cash: float = Field(..., ge=0)
    total_quantity: float = Field(..., ge=0)
    sellable_quantity: float = Field(..., ge=0)
    pending_quantity: float = Field(..., ge=0)
    average_cost: float = Field(..., ge=0)
    realized_pnl: float
    created_at: datetime
    updated_at: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize position symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class SandboxTradeSettlementResponse(SandboxTradeAgentSchemaBase):
    """Response payload for one sandbox T+2 settlement ledger entry."""

    id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    asset_type: SandboxTradeSettlementAssetType
    status: SandboxTradeSettlementStatus
    amount: float | None = Field(default=None, ge=0)
    quantity: float | None = Field(default=None, ge=0)
    trade_date: str = Field(..., min_length=1)
    settle_at: datetime
    settled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize settlement symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class SandboxTradeSettlementListResponse(SandboxTradeAgentSchemaBase):
    """Paginated settlement history for one sandbox session."""

    items: list[SandboxTradeSettlementResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default=DEFAULT_STOCK_PAGE_SIZE,
        ge=1,
        le=MAX_STOCK_PAGE_SIZE,
    )


class SandboxTradePortfolioSnapshotResponse(SandboxTradeAgentSchemaBase):
    """Response payload for one portfolio accounting snapshot."""

    id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    tick_id: str | None = Field(default=None, min_length=1)
    symbol: str = Field(..., min_length=1, max_length=MAX_STOCK_RESEARCH_SYMBOL_LENGTH)
    available_cash: float = Field(..., ge=0)
    pending_cash: float = Field(..., ge=0)
    total_quantity: float = Field(..., ge=0)
    sellable_quantity: float = Field(..., ge=0)
    pending_quantity: float = Field(..., ge=0)
    latest_price: float | None = Field(default=None, ge=0)
    market_value: float = Field(..., ge=0)
    equity: float = Field(..., ge=0)
    realized_pnl: float
    unrealized_pnl: float | None = None
    created_at: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize snapshot symbols into uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class SandboxTradePortfolioSnapshotListResponse(SandboxTradeAgentSchemaBase):
    """Paginated portfolio snapshots for one sandbox session."""

    items: list[SandboxTradePortfolioSnapshotResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default=DEFAULT_STOCK_PAGE_SIZE,
        ge=1,
        le=MAX_STOCK_PAGE_SIZE,
    )


class SandboxTradePortfolioStateResponse(SandboxTradeAgentSchemaBase):
    """Current portfolio state returned by sandbox trade-agent APIs."""

    position: SandboxTradePositionResponse
    latest_snapshot: SandboxTradePortfolioSnapshotResponse | None = None
    pending_settlements: list[SandboxTradeSettlementResponse] = Field(
        default_factory=list
    )
