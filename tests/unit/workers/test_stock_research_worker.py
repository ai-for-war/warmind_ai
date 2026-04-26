from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

import app.workers.stock_research_worker as stock_research_worker
from app.agents.implementations.stock_research_agent.runtime import (
    StockResearchAgentRuntimeConfig,
)
from app.domain.models.stock_research_report import (
    StockResearchReport,
    StockResearchReportRuntimeConfig,
    StockResearchReportStatus,
)
from app.workers.stock_research_worker import StockResearchWorker


def _utc() -> datetime:
    return datetime(2026, 4, 24, 8, tzinfo=timezone.utc)


def _runtime_config() -> StockResearchReportRuntimeConfig:
    return StockResearchReportRuntimeConfig(
        provider="openai",
        model="gpt-5.2",
        reasoning="high",
    )


def _report(
    *,
    report_id: str = "report-1",
    symbol: str = "FPT",
    status: StockResearchReportStatus = StockResearchReportStatus.QUEUED,
) -> StockResearchReport:
    return StockResearchReport(
        _id=report_id,
        user_id="user-1",
        organization_id="org-1",
        symbol=symbol,
        status=status,
        runtime_config=_runtime_config(),
        created_at=_utc(),
        updated_at=_utc(),
    )


class _Queue:
    def __init__(
        self,
        payload: dict[str, object] | list[dict[str, object]] | None,
    ) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def dequeue(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.payload, list):
            if not self.payload:
                return None
            return self.payload.pop(0)
        return self.payload


class _ReportRepo:
    def __init__(
        self,
        *,
        claimed: StockResearchReport | None,
        existing: StockResearchReport | None = None,
    ) -> None:
        self.claimed = claimed
        self.existing = existing
        self.claim_calls: list[str] = []
        self.find_calls: list[str] = []

    async def claim_queued_report(self, report_id: str):
        self.claim_calls.append(report_id)
        return self.claimed

    async def find_by_id(self, report_id: str):
        self.find_calls.append(report_id)
        return self.existing


class _Service:
    def __init__(self) -> None:
        self.process_calls: list[dict[str, object]] = []

    async def process_report(self, **kwargs) -> None:
        self.process_calls.append(kwargs)


class _ReportRepoById:
    def __init__(self, reports: dict[str, StockResearchReport]) -> None:
        self.reports = reports
        self.claim_calls: list[str] = []

    async def claim_queued_report(self, report_id: str):
        self.claim_calls.append(report_id)
        return self.reports.get(report_id)

    async def find_by_id(self, report_id: str):
        return self.reports.get(report_id)


class _BlockingService:
    def __init__(self, *, expected_started: int) -> None:
        self.expected_started = expected_started
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.process_calls: list[dict[str, object]] = []

    async def process_report(self, **kwargs) -> None:
        self.process_calls.append(kwargs)
        if len(self.process_calls) >= self.expected_started:
            self.started.set()
        await self.release.wait()


class _Settings:
    MONGODB_URI = "mongodb://localhost:27017"
    MONGODB_DB_NAME = "test"
    REDIS_URL = "redis://localhost:6379/0"


class _MCPManager:
    def __init__(self) -> None:
        self.tool_count = 2
        self.raw_tool_count = 2
        self.missing_normalized_tool_names: list[str] = []
        self.initialize_calls: list[object] = []

    async def initialize(self, config: object) -> None:
        self.initialize_calls.append(config)


def _payload(
    *,
    report_id: str = "report-1",
    symbol: str = "fpt",
) -> dict[str, object]:
    return {
        "report_id": report_id,
        "symbol": symbol,
        "runtime_config": {
            "provider": "openai",
            "model": "gpt-5.2",
            "reasoning": "high",
        },
    }


@pytest.mark.asyncio
async def test_setup_connections_initializes_mongodb_redis_and_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    mcp_manager = _MCPManager()

    async def fake_mongodb_connect(**kwargs) -> None:
        calls.append(("mongodb", kwargs))

    async def fake_redis_connect(**kwargs) -> None:
        calls.append(("redis", kwargs))

    monkeypatch.setattr(stock_research_worker, "get_settings", lambda: _Settings())
    monkeypatch.setattr(stock_research_worker.MongoDB, "connect", fake_mongodb_connect)
    monkeypatch.setattr(
        stock_research_worker.RedisClient,
        "connect",
        fake_redis_connect,
    )
    monkeypatch.setattr(
        stock_research_worker,
        "get_mcp_tools_manager",
        lambda: mcp_manager,
    )

    await stock_research_worker.setup_connections()

    assert calls == [
        (
            "mongodb",
            {
                "uri": _Settings.MONGODB_URI,
                "db_name": _Settings.MONGODB_DB_NAME,
            },
        ),
        ("redis", {"url": _Settings.REDIS_URL}),
    ]
    assert mcp_manager.initialize_calls == [stock_research_worker.MCP_SERVERS]


@pytest.mark.asyncio
async def test_run_once_processes_queued_report_through_stock_research_service() -> None:
    worker = StockResearchWorker()
    queue = _Queue(_payload())
    repo = _ReportRepo(claimed=_report())
    service = _Service()
    worker._queue = queue
    worker._report_repo = repo
    worker._service = service

    processed = await worker.run_once()
    await worker._wait_for_active_tasks()

    assert processed is True
    assert queue.calls == [
        {
            "queue_name": worker.settings.STOCK_RESEARCH_QUEUE_NAME,
            "timeout": worker.DEQUEUE_TIMEOUT,
        }
    ]
    assert repo.claim_calls == ["report-1"]
    assert repo.find_calls == []
    assert len(service.process_calls) == 1
    process_call = service.process_calls[0]
    assert process_call["report_id"] == "report-1"
    assert process_call["symbol"] == "FPT"
    assert process_call["runtime_config"] == StockResearchAgentRuntimeConfig(
        provider="openai",
        model="gpt-5.2",
        reasoning="high",
    )


@pytest.mark.asyncio
async def test_run_once_skips_missing_report_after_lost_claim() -> None:
    worker = StockResearchWorker()
    repo = _ReportRepo(claimed=None, existing=None)
    service = _Service()
    worker._queue = _Queue(_payload())
    worker._report_repo = repo
    worker._service = service

    processed = await worker.run_once()
    await worker._wait_for_active_tasks()

    assert processed is True
    assert repo.claim_calls == ["report-1"]
    assert repo.find_calls == ["report-1"]
    assert service.process_calls == []


@pytest.mark.asyncio
async def test_run_once_skips_report_that_is_already_terminal() -> None:
    worker = StockResearchWorker()
    repo = _ReportRepo(
        claimed=None,
        existing=_report(status=StockResearchReportStatus.COMPLETED),
    )
    service = _Service()
    worker._queue = _Queue(_payload())
    worker._report_repo = repo
    worker._service = service

    processed = await worker.run_once()
    await worker._wait_for_active_tasks()

    assert processed is True
    assert repo.find_calls == ["report-1"]
    assert service.process_calls == []


@pytest.mark.asyncio
async def test_run_once_discards_invalid_payload_without_claiming_report() -> None:
    worker = StockResearchWorker()
    repo = _ReportRepo(claimed=_report())
    service = _Service()
    worker._queue = _Queue({"report_id": "report-1", "symbol": ""})
    worker._report_repo = repo
    worker._service = service

    processed = await worker.run_once()

    assert processed is True
    assert repo.claim_calls == []
    assert service.process_calls == []


@pytest.mark.asyncio
async def test_run_once_dispatches_multiple_tasks_concurrently() -> None:
    worker = StockResearchWorker()
    worker.max_concurrency = 2
    worker._semaphore = asyncio.Semaphore(worker.max_concurrency)
    queue = _Queue(
        [
            _payload(report_id="report-1", symbol="fpt"),
            _payload(report_id="report-2", symbol="vcb"),
        ]
    )
    repo = _ReportRepoById(
        {
            "report-1": _report(report_id="report-1", symbol="FPT"),
            "report-2": _report(report_id="report-2", symbol="VCB"),
        }
    )
    service = _BlockingService(expected_started=2)
    worker._queue = queue
    worker._report_repo = repo
    worker._service = service

    first_dispatched = await worker.run_once()
    second_dispatched = await worker.run_once()
    await asyncio.wait_for(service.started.wait(), timeout=1)

    assert first_dispatched is True
    assert second_dispatched is True
    assert len(worker._active_tasks) == 2
    assert repo.claim_calls == ["report-1", "report-2"]
    assert [call["report_id"] for call in service.process_calls] == [
        "report-1",
        "report-2",
    ]

    service.release.set()
    await worker._wait_for_active_tasks()

    assert worker._active_tasks == set()


def test_stop_clears_running_flag() -> None:
    worker = StockResearchWorker()
    worker.running = True

    worker.stop()

    assert worker.running is False
