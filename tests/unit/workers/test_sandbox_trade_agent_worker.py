from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.domain.models.sandbox_trade_agent import (
    SandboxTradeAction,
    SandboxTradeDecision,
    SandboxTradeMarketSnapshot,
    SandboxTradePosition,
    SandboxTradeQuantityType,
    SandboxTradeSession,
    SandboxTradeSessionStatus,
    SandboxTradeTick,
    SandboxTradeTickStatus,
)
from app.domain.schemas.sandbox_trade_task import SandboxTradeTickTask
from app.services.stocks.sandbox_trade_dispatcher_service import (
    SandboxTradeAgentDispatcherService,
)
from app.workers.sandbox_trade_agent_worker import SandboxTradeAgentWorker


def _utc(
    year: int = 2026,
    month: int = 5,
    day: int = 4,
    hour: int = 2,
    minute: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _session(
    *,
    next_run_at: datetime | None = None,
    status: SandboxTradeSessionStatus = SandboxTradeSessionStatus.ACTIVE,
) -> SandboxTradeSession:
    return SandboxTradeSession(
        _id="session-1",
        user_id="user-1",
        organization_id="org-1",
        symbol="FPT",
        status=status,
        initial_capital=100_000_000,
        next_run_at=next_run_at or _utc(),
        created_at=_utc(),
        updated_at=_utc(),
    )


def _tick(
    *,
    status: SandboxTradeTickStatus = SandboxTradeTickStatus.RUNNING,
    tick_id: str = "tick-1",
    lock_token: str = "lock-1",
    decision: SandboxTradeDecision | None = None,
) -> SandboxTradeTick:
    return SandboxTradeTick(
        _id=tick_id,
        session_id="session-1",
        tick_at=_utc(),
        status=status,
        lock_token=lock_token,
        lock_expires_at=_utc() + timedelta(minutes=10),
        market_snapshot=SandboxTradeMarketSnapshot(
            symbol="FPT",
            source="VCI",
            latest_price=100_000,
            observed_at=_utc(),
        ),
        decision=decision,
        created_at=_utc(),
        updated_at=_utc(),
    )


def _decision(action: SandboxTradeAction) -> SandboxTradeDecision:
    if action == SandboxTradeAction.HOLD:
        return SandboxTradeDecision(action=action, reason="hold")
    return SandboxTradeDecision(
        action=action,
        quantity_type=SandboxTradeQuantityType.SHARES,
        quantity_value=1,
        reason="trade",
    )


def _position() -> SandboxTradePosition:
    return SandboxTradePosition(
        _id="position-1",
        session_id="session-1",
        symbol="FPT",
        available_cash=100_000_000,
        total_quantity=0,
        sellable_quantity=0,
        pending_quantity=0,
        average_cost=0,
        created_at=_utc(),
        updated_at=_utc(),
    )


class _DispatchSessionRepo:
    def __init__(self, sessions: list[SandboxTradeSession]) -> None:
        self.sessions = sessions
        self.advance_calls: list[dict[str, object]] = []

    async def list_due_active_sessions(self, **kwargs) -> list[SandboxTradeSession]:
        due_at = kwargs["due_at"]
        return [
            session
            for session in self.sessions
            if session.status == SandboxTradeSessionStatus.ACTIVE
            and session.next_run_at <= due_at
        ]

    async def advance_next_run_at(self, **kwargs):
        self.advance_calls.append(kwargs)


class _DispatchTickRepo:
    def __init__(self) -> None:
        self.ticks: dict[tuple[str, datetime], SandboxTradeTick] = {}
        self.create_calls = 0
        self.claim_stale_calls = 0
        self._lock = asyncio.Lock()

    async def create_dispatching(self, **kwargs) -> SandboxTradeTick | None:
        async with self._lock:
            self.create_calls += 1
            key = (kwargs["session_id"], kwargs["tick_at"])
            if key in self.ticks:
                return None
            tick = _tick(
                status=SandboxTradeTickStatus.DISPATCHING,
                tick_id=f"tick-{len(self.ticks) + 1}",
                lock_token=f"lock-{len(self.ticks) + 1}",
            ).model_copy(
                update={
                    "session_id": kwargs["session_id"],
                    "tick_at": kwargs["tick_at"],
                    "lock_expires_at": kwargs["lock_expires_at"],
                }
            )
            self.ticks[key] = tick
            return tick

    async def claim_stale_dispatch(self, **kwargs) -> SandboxTradeTick | None:
        self.claim_stale_calls += 1
        key = (kwargs["session_id"], kwargs["tick_at"])
        tick = self.ticks.get(key)
        if tick is None or tick.lock_expires_at > kwargs["now"]:
            return None
        updated = tick.model_copy(
            update={
                "status": SandboxTradeTickStatus.DISPATCHING,
                "lock_token": f"recovered-{self.claim_stale_calls}",
                "lock_expires_at": kwargs["lock_expires_at"],
            }
        )
        self.ticks[key] = updated
        return updated

    async def release_dispatch_after_enqueue_failure(self, **kwargs):
        return None


class _QueueService:
    def __init__(self, success: bool = True) -> None:
        self.success = success
        self.calls: list[dict[str, object]] = []

    async def enqueue_tick_model(self, **kwargs) -> bool:
        self.calls.append(kwargs)
        return self.success


def _dispatcher(
    *,
    session_repo: _DispatchSessionRepo,
    tick_repo: _DispatchTickRepo,
    queue_service: _QueueService | None = None,
) -> SandboxTradeAgentDispatcherService:
    return SandboxTradeAgentDispatcherService(
        session_repo=session_repo,
        tick_repo=tick_repo,
        queue_service=queue_service or _QueueService(),
        windows=(),
    )


@pytest.mark.asyncio
async def test_dispatcher_repeated_calls_for_same_tick_enqueue_once() -> None:
    session_repo = _DispatchSessionRepo([_session(next_run_at=_utc())])
    tick_repo = _DispatchTickRepo()
    queue_service = _QueueService()
    dispatcher = _dispatcher(
        session_repo=session_repo,
        tick_repo=tick_repo,
        queue_service=queue_service,
    )

    first = await dispatcher.dispatch_due(now=_utc())
    second = await dispatcher.dispatch_due(now=_utc())

    assert first.dispatched == 1
    assert second.dispatched == 0
    assert second.skipped == 1
    assert len(tick_repo.ticks) == 1
    assert len(queue_service.calls) == 1


@pytest.mark.asyncio
async def test_dispatcher_concurrent_claims_create_one_tick() -> None:
    tick_repo = _DispatchTickRepo()

    results = await asyncio.gather(
        *[
            tick_repo.create_dispatching(
                session_id="session-1",
                tick_at=_utc(),
                lock_expires_at=_utc() + timedelta(minutes=10),
            )
            for _ in range(5)
        ]
    )

    assert len([tick for tick in results if tick is not None]) == 1
    assert len(tick_repo.ticks) == 1
    assert tick_repo.create_calls == 5


@pytest.mark.asyncio
async def test_dispatcher_recovers_stale_tick_claim() -> None:
    session_repo = _DispatchSessionRepo([_session(next_run_at=_utc())])
    tick_repo = _DispatchTickRepo()
    stale = await tick_repo.create_dispatching(
        session_id="session-1",
        tick_at=_utc(),
        lock_expires_at=_utc() - timedelta(minutes=1),
    )
    assert stale is not None
    queue_service = _QueueService()
    dispatcher = _dispatcher(
        session_repo=session_repo,
        tick_repo=tick_repo,
        queue_service=queue_service,
    )

    result = await dispatcher.dispatch_due(now=_utc())

    assert result.dispatched == 1
    assert result.recovered == 1
    assert tick_repo.claim_stale_calls == 1
    assert queue_service.calls[0]["tick"].lock_token == "recovered-1"


class _WorkerQueue:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def dequeue(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class _WorkerTickRepo:
    def __init__(self, claimed_tick: SandboxTradeTick | None) -> None:
        self.claimed_tick = claimed_tick
        self.claim_calls: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []

    async def claim_for_processing(self, **kwargs):
        self.claim_calls.append(kwargs)
        return self.claimed_tick

    async def list_by_session(self, **kwargs):
        return [], 0

    async def mark_failed(self, **kwargs):
        self.failed.append(kwargs)
        return self.claimed_tick.model_copy(
            update={"status": SandboxTradeTickStatus.FAILED}
        )


class _WorkerSessionRepo:
    def __init__(self, session: SandboxTradeSession | None) -> None:
        self.session = session
        self.advance_calls: list[dict[str, object]] = []

    async def find_by_id(self, **kwargs):
        return self.session

    async def advance_next_run_at(self, **kwargs):
        self.advance_calls.append(kwargs)


class _WorkerExecutionService:
    def __init__(self, terminal_tick: SandboxTradeTick) -> None:
        self.terminal_tick = terminal_tick
        self.apply_calls: list[dict[str, object]] = []
        self.execute_calls: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []

    async def apply_due_settlements(self, **kwargs):
        self.apply_calls.append(kwargs)
        return _position()

    async def execute_tick_decision(self, **kwargs):
        self.execute_calls.append(kwargs)
        return SimpleNamespace(tick=self.terminal_tick, position=_position())

    async def record_failed_tick(self, **kwargs):
        self.failed.append(kwargs)
        return kwargs["tick"].model_copy(
            update={"status": SandboxTradeTickStatus.FAILED}
        )


class _WorkerMarketDataService:
    def __init__(self, *, should_continue: bool, tick: SandboxTradeTick) -> None:
        self.should_continue = should_continue
        self.tick = tick
        self.calls: list[dict[str, object]] = []

    async def prepare_tick_market_data(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(tick=self.tick, should_continue=self.should_continue)


class _WorkerRuntimeService:
    def __init__(self, tick: SandboxTradeTick) -> None:
        self.tick = tick
        self.calls: list[dict[str, object]] = []

    async def invoke_for_tick(self, **kwargs):
        self.calls.append(kwargs)
        return self.tick


class _WorkerSettlementRepo:
    async def list_pending_by_session(self, **kwargs):
        return []


class _WorkerSnapshotService:
    def __init__(self) -> None:
        self.snapshot_repo = self

    async def find_latest_by_session(self, **kwargs):
        return None


def _task() -> SandboxTradeTickTask:
    return SandboxTradeTickTask(
        session_id="session-1",
        tick_id="tick-1",
        lock_token="lock-1",
        symbol="FPT",
        tick_at=_utc(),
    )


def _worker(
    *,
    tick_repo: _WorkerTickRepo,
    session_repo: _WorkerSessionRepo,
    market_data_service: _WorkerMarketDataService,
    runtime_service: _WorkerRuntimeService,
    execution_service: _WorkerExecutionService,
) -> SandboxTradeAgentWorker:
    worker = SandboxTradeAgentWorker()
    worker.settings = SimpleNamespace(
        SANDBOX_TRADE_AGENT_QUEUE_NAME="sandbox_trade_agent_tasks",
        SANDBOX_TRADE_AGENT_TICK_LOCK_SECONDS=600,
        SANDBOX_TRADE_AGENT_CADENCE_SECONDS=180,
        SANDBOX_TRADE_AGENT_WORKER_POLL_INTERVAL_SECONDS=30,
        SANDBOX_TRADE_AGENT_TRADING_WINDOWS=["09:00-11:30", "13:00-14:45"],
    )
    worker._tick_repo = tick_repo
    worker._session_repo = session_repo
    worker._position_repo = SimpleNamespace()
    worker._settlement_repo = _WorkerSettlementRepo()
    worker._market_data_service = market_data_service
    worker._runtime_service = runtime_service
    worker._execution_service = execution_service
    worker._snapshot_service = _WorkerSnapshotService()
    return worker


@pytest.mark.asyncio
async def test_worker_processes_skipped_market_data_tick_and_advances_session() -> None:
    skipped_tick = _tick(status=SandboxTradeTickStatus.SKIPPED)
    execution_service = _WorkerExecutionService(skipped_tick)
    worker = _worker(
        tick_repo=_WorkerTickRepo(_tick()),
        session_repo=_WorkerSessionRepo(_session()),
        market_data_service=_WorkerMarketDataService(
            should_continue=False,
            tick=skipped_tick,
        ),
        runtime_service=_WorkerRuntimeService(skipped_tick),
        execution_service=execution_service,
    )

    processed = await worker.process_task(_task())

    assert processed is True
    assert worker._session_repo.advance_calls
    assert worker._runtime_service.calls == []
    assert execution_service.execute_calls == []


@pytest.mark.asyncio
async def test_worker_processes_valid_hold_decision() -> None:
    decided_tick = _tick(decision=_decision(SandboxTradeAction.HOLD))
    completed_tick = decided_tick.model_copy(
        update={"status": SandboxTradeTickStatus.COMPLETED}
    )
    execution_service = _WorkerExecutionService(completed_tick)
    worker = _worker(
        tick_repo=_WorkerTickRepo(_tick()),
        session_repo=_WorkerSessionRepo(_session()),
        market_data_service=_WorkerMarketDataService(
            should_continue=True,
            tick=_tick(),
        ),
        runtime_service=_WorkerRuntimeService(decided_tick),
        execution_service=execution_service,
    )

    processed = await worker.process_task(_task())

    assert processed is True
    assert worker._runtime_service.calls
    assert execution_service.execute_calls
    assert worker._session_repo.advance_calls


@pytest.mark.asyncio
async def test_worker_processes_valid_trade_decision() -> None:
    decided_tick = _tick(decision=_decision(SandboxTradeAction.BUY))
    completed_tick = decided_tick.model_copy(
        update={"status": SandboxTradeTickStatus.COMPLETED, "order_id": "order-1"}
    )
    execution_service = _WorkerExecutionService(completed_tick)
    worker = _worker(
        tick_repo=_WorkerTickRepo(_tick()),
        session_repo=_WorkerSessionRepo(_session()),
        market_data_service=_WorkerMarketDataService(
            should_continue=True,
            tick=_tick(),
        ),
        runtime_service=_WorkerRuntimeService(decided_tick),
        execution_service=execution_service,
    )

    processed = await worker.process_task(_task())

    assert processed is True
    assert execution_service.execute_calls[0]["tick"].decision.action == (
        SandboxTradeAction.BUY
    )
    assert worker._session_repo.advance_calls


@pytest.mark.asyncio
async def test_worker_advances_invalid_agent_output_without_execution() -> None:
    rejected_tick = _tick(status=SandboxTradeTickStatus.REJECTED).model_copy(
        update={"rejection_reason": "INVALID_AGENT_DECISION"}
    )
    execution_service = _WorkerExecutionService(rejected_tick)
    worker = _worker(
        tick_repo=_WorkerTickRepo(_tick()),
        session_repo=_WorkerSessionRepo(_session()),
        market_data_service=_WorkerMarketDataService(
            should_continue=True,
            tick=_tick(),
        ),
        runtime_service=_WorkerRuntimeService(rejected_tick),
        execution_service=execution_service,
    )

    processed = await worker.process_task(_task())

    assert processed is True
    assert worker._runtime_service.calls
    assert execution_service.execute_calls == []
    assert worker._session_repo.advance_calls
