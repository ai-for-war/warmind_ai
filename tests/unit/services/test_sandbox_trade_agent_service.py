from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.common.exceptions import (
    SandboxTradeSessionNotFoundError,
    StockSymbolNotFoundError,
)
from app.domain.models.sandbox_trade_agent import (
    SandboxTradeSession,
    SandboxTradeSessionStatus,
)
from app.domain.models.user import User
from app.domain.schemas.sandbox_trade_agent import (
    DEFAULT_SANDBOX_TRADE_INITIAL_CAPITAL,
    SandboxTradeSessionCreateRequest,
)
from app.services.stocks.sandbox_trade_agent_service import (
    SandboxTradeAgentSessionService,
)


def _utc(
    year: int = 2026,
    month: int = 5,
    day: int = 4,
    hour: int = 2,
) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _user(user_id: str = "user-1") -> User:
    return User(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=_utc(),
        updated_at=_utc(),
    )


def _session(
    *,
    session_id: str = "session-1",
    symbol: str = "FPT",
    initial_capital: float = DEFAULT_SANDBOX_TRADE_INITIAL_CAPITAL,
) -> SandboxTradeSession:
    return SandboxTradeSession(
        _id=session_id,
        user_id="user-1",
        organization_id="org-1",
        symbol=symbol,
        status=SandboxTradeSessionStatus.ACTIVE,
        initial_capital=initial_capital,
        next_run_at=_utc(),
        created_at=_utc(),
        updated_at=_utc(),
    )


def _service(
    *,
    session_repo: object,
    position_repo: object | None = None,
    stock_exists: bool = True,
) -> SandboxTradeAgentSessionService:
    return SandboxTradeAgentSessionService(
        session_repo=session_repo,
        tick_repo=SimpleNamespace(),
        order_repo=SimpleNamespace(),
        position_repo=position_repo or SimpleNamespace(create_initial=AsyncMock()),
        settlement_repo=SimpleNamespace(),
        snapshot_repo=SimpleNamespace(),
        stock_repo=SimpleNamespace(
            exists_by_symbol=AsyncMock(return_value=stock_exists)
        ),
        next_run_at_factory=lambda: _utc(),
    )


@pytest.mark.asyncio
async def test_create_session_normalizes_symbol_and_uses_default_capital() -> None:
    session_repo = SimpleNamespace(
        create=AsyncMock(return_value=_session(symbol="FPT"))
    )
    position_repo = SimpleNamespace(create_initial=AsyncMock())
    service = _service(session_repo=session_repo, position_repo=position_repo)

    response = await service.create_session(
        current_user=_user(),
        organization_id="org-1",
        request=SandboxTradeSessionCreateRequest(symbol=" fpt "),
    )

    assert response.symbol == "FPT"
    assert response.initial_capital == DEFAULT_SANDBOX_TRADE_INITIAL_CAPITAL
    session_repo.create.assert_awaited_once()
    create_kwargs = session_repo.create.await_args.kwargs
    assert create_kwargs["user_id"] == "user-1"
    assert create_kwargs["organization_id"] == "org-1"
    assert create_kwargs["symbol"] == "FPT"
    assert create_kwargs["initial_capital"] == DEFAULT_SANDBOX_TRADE_INITIAL_CAPITAL
    position_repo.create_initial.assert_awaited_once_with(
        session_id="session-1",
        symbol="FPT",
        initial_capital=DEFAULT_SANDBOX_TRADE_INITIAL_CAPITAL,
    )


@pytest.mark.asyncio
async def test_create_session_rejects_unknown_symbol_without_persisting() -> None:
    session_repo = SimpleNamespace(create=AsyncMock())
    position_repo = SimpleNamespace(create_initial=AsyncMock())
    service = _service(
        session_repo=session_repo,
        position_repo=position_repo,
        stock_exists=False,
    )

    with pytest.raises(StockSymbolNotFoundError):
        await service.create_session(
            current_user=_user(),
            organization_id="org-1",
            request=SandboxTradeSessionCreateRequest(symbol="UNKNOWN"),
        )

    session_repo.create.assert_not_awaited()
    position_repo.create_initial.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_rejects_session_outside_user_or_organization_scope() -> None:
    session_repo = SimpleNamespace(find_owned_session=AsyncMock(return_value=None))
    service = _service(session_repo=session_repo)

    with pytest.raises(SandboxTradeSessionNotFoundError):
        await service.get_session(
            current_user=_user("other-user"),
            organization_id="other-org",
            session_id="session-1",
        )

    session_repo.find_owned_session.assert_awaited_once_with(
        session_id="session-1",
        user_id="other-user",
        organization_id="other-org",
    )
