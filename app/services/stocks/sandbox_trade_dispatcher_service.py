"""Dispatcher service for due sandbox trade-agent session ticks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.domain.models.sandbox_trade_agent import SandboxTradeSession
from app.repo.sandbox_trade_agent_repo import (
    SandboxTradeSessionRepository,
    SandboxTradeTickRepository,
)
from app.services.stocks.sandbox_trade_queue_service import SandboxTradeQueueService
from app.services.stocks.sandbox_trade_schedule_calculator import (
    DEFAULT_SANDBOX_TRADE_CADENCE_SECONDS,
    SandboxTradeTradingWindow,
    coerce_to_next_sandbox_trade_window,
    is_sandbox_trade_trading_time,
)

SANDBOX_TRADE_TICK_LOCK_SECONDS = 600


@dataclass(frozen=True)
class SandboxTradeAgentDispatchResult:
    """Summary of one sandbox trade-agent dispatcher pass."""

    scanned: int
    dispatched: int
    recovered: int
    skipped: int
    enqueue_failed: int


@dataclass(frozen=True)
class _DispatchOutcome:
    dispatched: bool = False
    recovered: bool = False
    enqueue_failed: bool = False


class SandboxTradeAgentDispatcherService:
    """Dispatch due active sandbox trade sessions into tick worker tasks."""

    def __init__(
        self,
        *,
        session_repo: SandboxTradeSessionRepository,
        tick_repo: SandboxTradeTickRepository,
        queue_service: SandboxTradeQueueService,
        windows: tuple[SandboxTradeTradingWindow, ...],
        cadence_seconds: int = DEFAULT_SANDBOX_TRADE_CADENCE_SECONDS,
        lock_seconds: int = SANDBOX_TRADE_TICK_LOCK_SECONDS,
    ) -> None:
        self.session_repo = session_repo
        self.tick_repo = tick_repo
        self.queue_service = queue_service
        self.windows = windows
        self.cadence_seconds = cadence_seconds
        self.lock_seconds = lock_seconds

    async def dispatch_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> SandboxTradeAgentDispatchResult:
        """Dispatch one bounded batch of due active sandbox trade sessions."""
        dispatch_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        sessions = await self.session_repo.list_due_active_sessions(
            due_at=dispatch_now,
            limit=limit,
        )

        dispatched = 0
        recovered = 0
        skipped = 0
        enqueue_failed = 0

        for session in sessions:
            outcome = await self._dispatch_session(
                session=session,
                now=dispatch_now,
            )
            if outcome.dispatched:
                dispatched += 1
            elif outcome.enqueue_failed:
                enqueue_failed += 1
            else:
                skipped += 1

            if outcome.recovered:
                recovered += 1

        return SandboxTradeAgentDispatchResult(
            scanned=len(sessions),
            dispatched=dispatched,
            recovered=recovered,
            skipped=skipped,
            enqueue_failed=enqueue_failed,
        )

    async def _dispatch_session(
        self,
        *,
        session: SandboxTradeSession,
        now: datetime,
    ) -> _DispatchOutcome:
        if session.id is None:
            return _DispatchOutcome()

        occurrence_at = session.next_run_at.astimezone(timezone.utc)
        if not self._can_dispatch_occurrence(occurrence_at=occurrence_at, now=now):
            await self._move_session_to_next_eligible_run(
                session=session,
                expected_next_run_at=occurrence_at,
                after=now,
            )
            return _DispatchOutcome()

        lock_expires_at = now + timedelta(seconds=self.lock_seconds)
        tick = await self.tick_repo.create_dispatching(
            session_id=session.id,
            tick_at=occurrence_at,
            lock_expires_at=lock_expires_at,
        )
        recovered = False
        if tick is None:
            tick = await self.tick_repo.claim_stale_dispatch(
                session_id=session.id,
                tick_at=occurrence_at,
                now=now,
                lock_expires_at=lock_expires_at,
            )
            recovered = tick is not None

        if tick is None or tick.id is None or tick.lock_token is None:
            return _DispatchOutcome()

        enqueue_succeeded = await self.queue_service.enqueue_tick_model(
            session=session,
            tick=tick,
        )
        if not enqueue_succeeded:
            await self.tick_repo.release_dispatch_after_enqueue_failure(
                tick_id=tick.id,
                lock_token=tick.lock_token,
                now=now,
                error="QUEUE_ENQUEUE_FAILED",
            )
            return _DispatchOutcome(recovered=recovered, enqueue_failed=True)

        return _DispatchOutcome(dispatched=True, recovered=recovered)

    def _can_dispatch_occurrence(
        self,
        *,
        occurrence_at: datetime,
        now: datetime,
    ) -> bool:
        """Require both scheduled occurrence and dispatch time to be tradable."""
        return is_sandbox_trade_trading_time(
            occurrence_at,
            windows=self.windows,
        ) and is_sandbox_trade_trading_time(now, windows=self.windows)

    async def _move_session_to_next_eligible_run(
        self,
        *,
        session: SandboxTradeSession,
        expected_next_run_at: datetime,
        after: datetime,
    ) -> None:
        next_run_at = coerce_to_next_sandbox_trade_window(after, windows=self.windows)
        await self.session_repo.advance_next_run_at(
            session_id=session.id,
            expected_next_run_at=expected_next_run_at,
            next_run_at=next_run_at,
        )
