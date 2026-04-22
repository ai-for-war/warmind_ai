from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.common.exceptions import StockSymbolNotFoundError
from app.domain.models.stock_research_report import (
    StockResearchReport,
    StockResearchReportFailure,
    StockResearchReportSource,
    StockResearchReportStatus,
)
from app.domain.models.user import User, UserRole
from app.domain.schemas.stock_research_report import (
    StockResearchReportCreateRequest,
    StockResearchReportRuntimeConfigRequest,
)
from app.services.stocks.stock_research_service import StockResearchService
import app.services.stocks.stock_research_service as stock_research_service_module


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _user(*, user_id: str = "user-1") -> User:
    now = _utc(2026, 4, 22, 8)
    return User(
        _id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="hashed",
        role=UserRole.USER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _report(
    *,
    report_id: str = "report-1",
    user_id: str = "user-1",
    organization_id: str = "org-1",
    symbol: str = "FPT",
    status: StockResearchReportStatus = StockResearchReportStatus.QUEUED,
    content: str | None = None,
    sources: list[StockResearchReportSource] | None = None,
    error: StockResearchReportFailure | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> StockResearchReport:
    now = _utc(2026, 4, 22, 8)
    return StockResearchReport(
        _id=report_id,
        user_id=user_id,
        organization_id=organization_id,
        symbol=symbol,
        status=status,
        content=content,
        sources=sources or [],
        error=error,
        created_at=now,
        started_at=started_at,
        completed_at=completed_at,
        updated_at=completed_at or started_at or now,
    )


def _service() -> tuple[StockResearchService, SimpleNamespace, SimpleNamespace]:
    report_repo = SimpleNamespace(
        create=AsyncMock(),
        find_owned_report=AsyncMock(),
        list_by_user_and_organization=AsyncMock(),
        update_lifecycle_state=AsyncMock(),
    )
    stock_repo = SimpleNamespace(exists_by_symbol=AsyncMock())
    return (
        StockResearchService(report_repo=report_repo, stock_repo=stock_repo),
        report_repo,
        stock_repo,
    )


@pytest.mark.asyncio
async def test_create_report_request_validates_symbol_against_catalog_and_persists_queued_report() -> None:
    service, report_repo, stock_repo = _service()
    current_user = _user()
    queued_report = _report(status=StockResearchReportStatus.QUEUED, symbol="FPT")
    stock_repo.exists_by_symbol.return_value = True
    report_repo.create.return_value = queued_report

    response = await service.create_report_request(
        current_user=current_user,
        organization_id="org-1",
        request=StockResearchReportCreateRequest(symbol=" fpt "),
    )

    stock_repo.exists_by_symbol.assert_awaited_once_with("FPT")
    report_repo.create.assert_awaited_once()
    assert report_repo.create.await_args.kwargs["status"] == StockResearchReportStatus.QUEUED
    assert response.id == queued_report.id
    assert response.symbol == "FPT"
    assert response.status == StockResearchReportStatus.QUEUED


@pytest.mark.asyncio
async def test_create_report_request_rejects_unknown_symbol() -> None:
    service, report_repo, stock_repo = _service()
    stock_repo.exists_by_symbol.return_value = False

    with pytest.raises(StockSymbolNotFoundError):
        await service.create_report_request(
            current_user=_user(),
            organization_id="org-1",
            request=StockResearchReportCreateRequest(symbol="unknown"),
        )

    report_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_report_request_validates_runtime_override_against_runtime_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, report_repo, stock_repo = _service()
    stock_repo.exists_by_symbol.return_value = True
    report_repo.create.return_value = _report()
    resolve_runtime = Mock(
        return_value=SimpleNamespace(provider="openai", model="gpt-5.2", reasoning="high")
    )
    monkeypatch.setattr(
        stock_research_service_module,
        "resolve_stock_research_runtime_config",
        resolve_runtime,
    )

    await service.create_report_request(
        current_user=_user(),
        organization_id="org-1",
        request=StockResearchReportCreateRequest(
            symbol="FPT",
            runtime_config=StockResearchReportRuntimeConfigRequest(
                provider="openai",
                model="gpt-5.2",
                reasoning="high",
            ),
        ),
    )

    resolve_runtime.assert_called_once_with(
        provider="openai",
        model="gpt-5.2",
        reasoning="high",
    )


@pytest.mark.asyncio
async def test_process_report_marks_completed_and_persists_markdown_and_sources() -> None:
    service, report_repo, _ = _service()
    source = StockResearchReportSource(
        source_id="S1",
        url="https://example.com/fpt",
        title="FPT Source",
    )
    report_repo.update_lifecycle_state.side_effect = [
        _report(status=StockResearchReportStatus.RUNNING, started_at=_utc(2026, 4, 22, 9)),
        _report(
            status=StockResearchReportStatus.COMPLETED,
            content="Current price is 95,800 VND. Evidence [S1]",
            sources=[source],
            started_at=_utc(2026, 4, 22, 9),
            completed_at=_utc(2026, 4, 22, 10),
        ),
    ]
    service._run_stock_research_agent = AsyncMock(  # type: ignore[method-assign]
        return_value=stock_research_service_module.StockResearchAgentOutput(
            content="Current price is 95,800 VND. Evidence [S1]",
            sources=[
                {
                    "source_id": source.source_id,
                    "url": source.url,
                    "title": source.title,
                }
            ],
        )
    )

    await service.process_report(report_id="report-1", symbol="FPT")

    assert report_repo.update_lifecycle_state.await_count == 2
    completed_kwargs = report_repo.update_lifecycle_state.await_args_list[1].kwargs
    assert completed_kwargs["status"] == StockResearchReportStatus.COMPLETED
    assert completed_kwargs["content"] == "Current price is 95,800 VND. Evidence [S1]"
    assert completed_kwargs["sources"] == [source]
    assert completed_kwargs["error"] is None


@pytest.mark.asyncio
async def test_process_report_marks_failed_and_clears_broken_artifacts() -> None:
    service, report_repo, _ = _service()
    report_repo.update_lifecycle_state.side_effect = [
        _report(status=StockResearchReportStatus.RUNNING, started_at=_utc(2026, 4, 22, 9)),
        _report(
            status=StockResearchReportStatus.FAILED,
            error=StockResearchReportFailure(code="RuntimeError", message="boom"),
            started_at=_utc(2026, 4, 22, 9),
            completed_at=_utc(2026, 4, 22, 10),
        ),
    ]
    service._run_stock_research_agent = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("boom")
    )

    await service.process_report(report_id="report-1", symbol="FPT")

    failed_kwargs = report_repo.update_lifecycle_state.await_args_list[1].kwargs
    assert failed_kwargs["status"] == StockResearchReportStatus.FAILED
    assert failed_kwargs["content"] is None
    assert failed_kwargs["sources"] == []
    assert failed_kwargs["error"] == StockResearchReportFailure(
        code="RuntimeError",
        message="boom",
    )


def test_extract_agent_output_accepts_uncited_current_price_text_when_web_sources_are_valid() -> None:
    output = StockResearchService._extract_agent_output(
        {
            "structured_response": {
                "content": (
                    "Current price is around 95,800 VND.\n\n"
                    "Business outlook remains resilient [S1]."
                ),
                "sources": [
                    {
                        "source_id": "S1",
                        "url": "https://example.com/fpt-outlook",
                        "title": "FPT Outlook",
                    }
                ],
            }
        }
    )

    assert "Current price is around 95,800 VND." in output.content
    assert output.sources[0].source_id == "S1"


def test_extract_agent_output_rejects_missing_citation_source() -> None:
    with pytest.raises(ValueError, match="missing source_id values: S2"):
        StockResearchService._extract_agent_output(
            {
                "structured_response": {
                    "content": "Thesis supported by [S2].",
                    "sources": [
                        {
                            "source_id": "S1",
                            "url": "https://example.com/fpt",
                            "title": "FPT Source",
                        }
                    ],
                }
            }
        )


def test_extract_agent_output_accepts_markdown_fallback_from_messages() -> None:
    output = StockResearchService._extract_agent_output(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": """
<think>
internal reasoning
</think>

## Thesis

FPT remains resilient [S1].

## Sources

- [S1] Example Source (https://example.com/fpt)
""".strip(),
                }
            ]
        }
    )

    assert output.content.startswith("## Thesis")
    assert output.sources[0].source_id == "S1"
