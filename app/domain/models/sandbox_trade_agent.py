"""Durable sandbox trade-agent persistence models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SandboxTradeSessionStatus(str, Enum):
    """Lifecycle states for one sandbox trade-agent session."""

    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    DELETED = "deleted"


class SandboxTradeTickStatus(str, Enum):
    """Execution lifecycle states for one session wake-up tick."""

    DISPATCHING = "dispatching"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    REJECTED = "rejected"


class SandboxTradeAction(str, Enum):
    """Autonomous actions the sandbox trade agent may request."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class SandboxTradeQuantityType(str, Enum):
    """Supported quantity modes in structured agent decisions."""

    SHARES = "shares"
    PERCENT_CASH = "percent_cash"
    PERCENT_POSITION = "percent_position"


class SandboxTradeOrderSide(str, Enum):
    """Sandbox order sides."""

    BUY = "buy"
    SELL = "sell"


class SandboxTradeOrderStatus(str, Enum):
    """Terminal sandbox order statuses for phase-1 immediate fills."""

    FILLED = "filled"
    REJECTED = "rejected"


class SandboxTradeSettlementAssetType(str, Enum):
    """Asset types settled by the sandbox T+2 ledger."""

    CASH = "cash"
    SECURITY = "security"


class SandboxTradeSettlementStatus(str, Enum):
    """Lifecycle states for sandbox settlement ledger entries."""

    PENDING = "pending"
    SETTLED = "settled"


class SandboxTradeModelBase(BaseModel):
    """Common persistence model settings for sandbox trade-agent documents."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class SandboxTradeAgentRuntimeConfig(SandboxTradeModelBase):
    """Resolved agent runtime configuration persisted with one session."""

    provider: str
    model: str
    reasoning: str | None = None

    @field_validator("provider", "model", mode="before")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        """Require persisted runtime identity fields to be non-blank strings."""
        if not isinstance(value, str):
            raise TypeError("runtime config fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("runtime config fields must not be blank")
        return normalized

    @field_validator("reasoning", mode="before")
    @classmethod
    def normalize_optional_reasoning(cls, value: str | None) -> str | None:
        """Collapse blank optional reasoning values to null."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("runtime reasoning must be a string or None")
        normalized = value.strip()
        return normalized or None


class SandboxTradeSession(SandboxTradeModelBase):
    """One user-owned autonomous paper-trading session stored in MongoDB."""

    id: str | None = Field(default=None, alias="_id")
    user_id: str
    organization_id: str
    symbol: str
    status: SandboxTradeSessionStatus = SandboxTradeSessionStatus.ACTIVE
    initial_capital: float = Field(..., gt=0)
    runtime_config: SandboxTradeAgentRuntimeConfig | None = None
    next_run_at: datetime
    last_tick_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    @field_validator("user_id", "organization_id", mode="before")
    @classmethod
    def normalize_scope_identifier(cls, value: str) -> str:
        """Require non-blank ownership identifiers."""
        if not isinstance(value, str):
            raise TypeError("ownership identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("ownership identifiers must not be blank")
        return normalized

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist sandbox symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator(
        "next_run_at",
        "last_tick_at",
        "created_at",
        "updated_at",
        "deleted_at",
    )
    @classmethod
    def normalize_optional_utc_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        """Persist session datetimes as timezone-aware UTC values."""
        if value is None:
            return None
        return _normalize_utc_datetime(value)


class SandboxTradeMarketSnapshot(SandboxTradeModelBase):
    """Market data snapshot persisted with one processable tick."""

    symbol: str
    source: str
    latest_price: float = Field(..., ge=0)
    observed_at: datetime | None = None
    summary: dict[str, object] = Field(default_factory=dict)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist market snapshot symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("source", mode="before")
    @classmethod
    def require_non_blank_source(cls, value: str) -> str:
        """Require a market data source label."""
        if not isinstance(value, str):
            raise TypeError("source must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("source must not be blank")
        return normalized

    @field_validator("observed_at")
    @classmethod
    def normalize_optional_observed_at(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        """Persist market observation time as timezone-aware UTC when present."""
        if value is None:
            return None
        return _normalize_utc_datetime(value)


class SandboxTradeDecision(SandboxTradeModelBase):
    """Structured autonomous decision returned by the sandbox trade agent."""

    action: SandboxTradeAction
    quantity_type: SandboxTradeQuantityType | None = None
    quantity_value: float | None = Field(default=None, gt=0)
    reason: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_notes: list[str] = Field(default_factory=list)

    @field_validator("reason", mode="before")
    @classmethod
    def require_non_blank_reason(cls, value: str) -> str:
        """Require the agent to explain its structured decision."""
        if not isinstance(value, str):
            raise TypeError("reason must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be blank")
        return normalized

    @field_validator("risk_notes", mode="before")
    @classmethod
    def normalize_risk_notes(cls, value: object) -> object:
        """Treat omitted risk notes as an empty list."""
        if value is None:
            return []
        return value


class SandboxTradeTick(SandboxTradeModelBase):
    """One idempotent wake-up occurrence for a sandbox trade-agent session."""

    id: str | None = Field(default=None, alias="_id")
    session_id: str
    tick_at: datetime
    status: SandboxTradeTickStatus = SandboxTradeTickStatus.DISPATCHING
    lock_expires_at: datetime | None = None
    lock_token: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    market_snapshot: SandboxTradeMarketSnapshot | None = None
    decision: SandboxTradeDecision | None = None
    order_id: str | None = None
    skip_reason: str | None = None
    rejection_reason: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("session_id", "order_id", "lock_token", mode="before")
    @classmethod
    def normalize_optional_identifier(cls, value: str | None) -> str | None:
        """Require persisted identifiers to be non-blank when present."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifiers must not be blank")
        return normalized

    @field_validator("skip_reason", "rejection_reason", "error", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Collapse blank optional diagnostic fields to null."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("diagnostic fields must be strings or None")
        normalized = value.strip()
        return normalized or None

    @field_validator(
        "tick_at",
        "lock_expires_at",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )
    @classmethod
    def normalize_optional_utc_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        """Persist tick datetimes as timezone-aware UTC values."""
        if value is None:
            return None
        return _normalize_utc_datetime(value)


class SandboxTradeOrder(SandboxTradeModelBase):
    """One sandbox order emitted from a validated agent decision."""

    id: str | None = Field(default=None, alias="_id")
    session_id: str
    tick_id: str
    symbol: str
    side: SandboxTradeOrderSide
    status: SandboxTradeOrderStatus
    quantity: float = Field(default=0, ge=0)
    price: float | None = Field(default=None, ge=0)
    gross_amount: float = Field(default=0, ge=0)
    rejection_reason: str | None = None
    filled_at: datetime | None = None
    trade_date: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("session_id", "tick_id", mode="before")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        """Require persisted identifiers to be non-blank."""
        if not isinstance(value, str):
            raise TypeError("identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifiers must not be blank")
        return normalized

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist order symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("rejection_reason", "trade_date", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Collapse blank optional order text to null."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("optional order text fields must be strings or None")
        normalized = value.strip()
        return normalized or None

    @field_validator("filled_at", "created_at", "updated_at")
    @classmethod
    def normalize_optional_utc_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        """Persist order datetimes as timezone-aware UTC values."""
        if value is None:
            return None
        return _normalize_utc_datetime(value)


class SandboxTradePosition(SandboxTradeModelBase):
    """Current cash and single-symbol position state for one sandbox session."""

    id: str | None = Field(default=None, alias="_id")
    session_id: str
    symbol: str
    available_cash: float = Field(..., ge=0)
    pending_cash: float = Field(default=0, ge=0)
    total_quantity: float = Field(default=0, ge=0)
    sellable_quantity: float = Field(default=0, ge=0)
    pending_quantity: float = Field(default=0, ge=0)
    average_cost: float = Field(default=0, ge=0)
    realized_pnl: float = 0
    created_at: datetime
    updated_at: datetime

    @field_validator("session_id", mode="before")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        """Require the session identifier to be non-blank."""
        if not isinstance(value, str):
            raise TypeError("session_id must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("session_id must not be blank")
        return normalized

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist position symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_utc_datetime(cls, value: datetime) -> datetime:
        """Persist position datetimes as timezone-aware UTC values."""
        return _normalize_utc_datetime(value)


class SandboxTradeSettlement(SandboxTradeModelBase):
    """One pending or settled T+2 sandbox ledger entry."""

    id: str | None = Field(default=None, alias="_id")
    session_id: str
    order_id: str
    symbol: str
    asset_type: SandboxTradeSettlementAssetType
    status: SandboxTradeSettlementStatus = SandboxTradeSettlementStatus.PENDING
    amount: float | None = Field(default=None, ge=0)
    quantity: float | None = Field(default=None, ge=0)
    trade_date: str
    settle_at: datetime
    settled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("session_id", "order_id", mode="before")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        """Require persisted identifiers to be non-blank."""
        if not isinstance(value, str):
            raise TypeError("identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifiers must not be blank")
        return normalized

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist settlement symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("trade_date", mode="before")
    @classmethod
    def normalize_trade_date(cls, value: str) -> str:
        """Require an ISO trade-date string for settlement auditability."""
        if not isinstance(value, str):
            raise TypeError("trade_date must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("trade_date must not be blank")
        return normalized

    @field_validator("settle_at", "settled_at", "created_at", "updated_at")
    @classmethod
    def normalize_optional_utc_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        """Persist settlement datetimes as timezone-aware UTC values."""
        if value is None:
            return None
        return _normalize_utc_datetime(value)


class SandboxTradePortfolioSnapshot(SandboxTradeModelBase):
    """Append-only portfolio accounting snapshot for one terminal tick."""

    id: str | None = Field(default=None, alias="_id")
    session_id: str
    tick_id: str | None = None
    symbol: str
    available_cash: float = Field(..., ge=0)
    pending_cash: float = Field(default=0, ge=0)
    total_quantity: float = Field(default=0, ge=0)
    sellable_quantity: float = Field(default=0, ge=0)
    pending_quantity: float = Field(default=0, ge=0)
    latest_price: float | None = Field(default=None, ge=0)
    market_value: float = Field(default=0, ge=0)
    equity: float = Field(..., ge=0)
    realized_pnl: float = 0
    unrealized_pnl: float | None = None
    created_at: datetime

    @field_validator("session_id", "tick_id", mode="before")
    @classmethod
    def normalize_optional_identifier(cls, value: str | None) -> str | None:
        """Require persisted identifiers to be non-blank when present."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("identifiers must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("identifiers must not be blank")
        return normalized

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Persist snapshot symbols in uppercase canonical form."""
        if not isinstance(value, str):
            raise TypeError("symbol must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized

    @field_validator("created_at")
    @classmethod
    def normalize_utc_datetime(cls, value: datetime) -> datetime:
        """Persist snapshot datetimes as timezone-aware UTC values."""
        return _normalize_utc_datetime(value)


def _normalize_utc_datetime(value: datetime) -> datetime:
    """Normalize one aware datetime to UTC for durable comparisons."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)
