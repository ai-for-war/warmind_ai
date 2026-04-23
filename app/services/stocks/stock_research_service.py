"""Service layer for asynchronous stock research report lifecycle orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import logging
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.agents.implementations.stock_research_agent.agent import (
    create_stock_research_agent,
)
from app.agents.implementations.stock_research_agent.runtime import (
    StockResearchAgentRuntimeConfig,
    resolve_stock_research_runtime_config,
)
from app.agents.implementations.stock_research_agent.validation import (
    StockResearchAgentOutput,
    parse_stock_research_output,
)
from app.common.exceptions import (
    StockResearchReportNotFoundError,
    StockSymbolNotFoundError,
)
from app.common.notification_types import NotificationTargetTypes, NotificationTypes
from app.domain.models.stock_research_report import (
    StockResearchReport,
    StockResearchReportFailure,
    StockResearchReportSource,
    StockResearchReportStatus,
)
from app.domain.models.user import User
from app.domain.schemas.stock_research_report import (
    StockResearchReportCreateRequest,
    StockResearchReportCreateResponse,
    StockResearchReportFailureResponse,
    StockResearchReportListResponse,
    StockResearchReportResponse,
    StockResearchReportSourceResponse,
    StockResearchReportSummary,
)
from app.repo.stock_research_report_repo import StockResearchReportRepository
from app.repo.stock_symbol_repo import StockSymbolRepository
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class StockResearchService:
    """Coordinate stock symbol validation, report persistence, and async execution."""

    def __init__(
        self,
        *,
        report_repo: StockResearchReportRepository,
        stock_repo: StockSymbolRepository,
        notification_service: NotificationService,
    ) -> None:
        self.report_repo = report_repo
        self.stock_repo = stock_repo
        self.notification_service = notification_service
        self._default_agent: CompiledStateGraph | None = None

    async def create_report_request(
        self,
        *,
        current_user: User,
        organization_id: str,
        request: StockResearchReportCreateRequest,
    ) -> StockResearchReportCreateResponse:
        """Validate one symbol and persist a queued report request."""
        symbol = request.symbol.strip().upper()
        self.resolve_request_runtime_config(request)
        if not await self.stock_repo.exists_by_symbol(symbol):
            raise StockSymbolNotFoundError()

        report = await self.report_repo.create(
            user_id=current_user.id,
            organization_id=organization_id,
            symbol=symbol,
            status=StockResearchReportStatus.QUEUED,
        )

        return self._to_create_response(report)

    async def get_report(
        self,
        *,
        current_user: User,
        organization_id: str,
        report_id: str,
    ) -> StockResearchReportResponse:
        """Read one caller-owned stock research report."""
        report = await self.report_repo.find_owned_report(
            report_id=report_id,
            user_id=current_user.id,
            organization_id=organization_id,
        )
        if report is None:
            raise StockResearchReportNotFoundError()
        return self._to_detail_response(report)

    async def list_reports(
        self,
        *,
        current_user: User,
        organization_id: str,
        symbol: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> StockResearchReportListResponse:
        """List one caller's stock research report history in an organization."""
        reports, total = await self.report_repo.list_by_user_and_organization(
            user_id=current_user.id,
            organization_id=organization_id,
            symbol=symbol,
            page=page,
            page_size=page_size,
        )
        return StockResearchReportListResponse(
            items=[self._to_summary(report) for report in reports],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def process_report(
        self,
        *,
        report_id: str,
        symbol: str,
        runtime_config: StockResearchAgentRuntimeConfig | None = None,
    ) -> None:
        """Advance one report through running and terminal lifecycle states."""
        started_at = datetime.now(timezone.utc)
        running_report = await self.report_repo.update_lifecycle_state(
            report_id=report_id,
            status=StockResearchReportStatus.RUNNING,
            started_at=started_at,
            completed_at=None,
            error=None,
        )
        if running_report is None:
            logger.warning(
                "Stock research report %s missing before processing", report_id
            )
            return

        terminal_report: StockResearchReport | None = None
        try:
            output = await self._run_stock_research_agent(
                company_name=symbol,
                symbol=symbol,
                runtime_config=runtime_config,
            )
            completed_report = await self.report_repo.update_lifecycle_state(
                report_id=report_id,
                status=StockResearchReportStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc),
                content=output.content,
                sources=[
                    StockResearchReportSource(
                        source_id=source.source_id,
                        url=source.url,
                        title=source.title,
                    )
                    for source in output.sources
                ],
                error=None,
            )
            if completed_report is not None:
                terminal_report = completed_report
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Stock research report %s failed during processing", report_id
            )
            failed_report = await self.report_repo.update_lifecycle_state(
                report_id=report_id,
                status=StockResearchReportStatus.FAILED,
                completed_at=datetime.now(timezone.utc),
                content=None,
                sources=[],
                error=self._to_failure_model(exc),
            )
            if failed_report is not None:
                terminal_report = failed_report

        if terminal_report is not None:
            await self._create_terminal_notification_best_effort(report=terminal_report)

    @staticmethod
    def _to_failure_model(exc: Exception) -> StockResearchReportFailure:
        """Convert one processing exception into stable persistence metadata."""
        code = type(exc).__name__.strip() or "StockResearchRunError"
        message = str(exc).strip() or "Stock research report generation failed"
        return StockResearchReportFailure(code=code, message=message)

    @staticmethod
    def resolve_request_runtime_config(
        request: StockResearchReportCreateRequest,
    ) -> StockResearchAgentRuntimeConfig | None:
        """Resolve an optional runtime override embedded in the create request."""
        if request.runtime_config is None:
            return None

        return resolve_stock_research_runtime_config(
            provider=request.runtime_config.provider,
            model=request.runtime_config.model,
            reasoning=request.runtime_config.reasoning,
        )

    async def _run_stock_research_agent(
        self,
        *,
        company_name: str,
        symbol: str,
        runtime_config: StockResearchAgentRuntimeConfig | None = None,
    ) -> StockResearchAgentOutput:
        """Run the dedicated stock research runtime from the service layer."""
        result = await self._get_agent(runtime_config).ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Generate a stock research report for the Vietnam-listed company "
                            f"{company_name} ({symbol})."
                        ),
                    }
                ]
            }
        )
        return self._extract_agent_output(result)

    def _get_agent(
        self,
        runtime_config: StockResearchAgentRuntimeConfig | None = None,
    ) -> CompiledStateGraph:
        """Return the cached stock research runtime for this service instance."""
        if runtime_config is None:
            if self._default_agent is None:
                self._default_agent = create_stock_research_agent()
            return self._default_agent

        return create_stock_research_agent(runtime_config)

    async def _create_terminal_notification_best_effort(
        self,
        *,
        report: StockResearchReport,
    ) -> None:
        """Best-effort notification creation that must not mutate report state."""
        try:
            await self._create_terminal_notification(report=report)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to create stock research notification for report %s",
                report.id,
            )

    async def _create_terminal_notification(
        self,
        *,
        report: StockResearchReport,
    ) -> None:
        """Create one inbox notification for terminal stock research states."""
        report_id = report.id
        if report_id is None:
            logger.warning(
                "Skipping stock research notification because report id is missing"
            )
            return

        if report.status == StockResearchReportStatus.COMPLETED:
            notification_type = NotificationTypes.STOCK_RESEARCH_REPORT_COMPLETED
            title = f"{report.symbol} research report is ready"
            body = (
                f"Open the {report.symbol} research report to review the completed "
                "analysis."
            )
        elif report.status == StockResearchReportStatus.FAILED:
            notification_type = NotificationTypes.STOCK_RESEARCH_REPORT_FAILED
            title = f"{report.symbol} research report failed"
            body = (
                f"Open the {report.symbol} research report to review the failure "
                "details."
            )
        else:
            return

        await self.notification_service.create_notification(
            user_id=report.user_id,
            organization_id=report.organization_id,
            type=notification_type,
            title=title,
            body=body,
            target_type=NotificationTargetTypes.STOCK_RESEARCH_REPORT,
            target_id=report_id,
            link=f"/stock-research/reports/{report_id}",
            dedupe_key=f"{notification_type}:{report_id}",
            metadata={
                "symbol": report.symbol,
                "report_status": report.status.value,
            },
        )

    @staticmethod
    def _extract_agent_output(
        result: Mapping[str, Any],
    ) -> StockResearchAgentOutput:
        """Extract validated output from a stock-research agent run result."""
        structured_response = result.get("structured_response")
        if structured_response is not None:
            if isinstance(structured_response, StockResearchAgentOutput):
                return structured_response
            if isinstance(structured_response, Mapping):
                return parse_stock_research_output(structured_response)
            raise ValueError(
                "stock research agent structured_response has an unsupported shape"
            )

        return parse_stock_research_output(
            StockResearchService._extract_final_response_text(result)
        )

    @staticmethod
    def _extract_final_response_text(result: Mapping[str, Any]) -> str:
        """Extract the final assistant text from a compiled agent response."""
        messages = result.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("stock research agent run returned no messages")

        for message in reversed(messages):
            content = StockResearchService._extract_message_content(message)
            if content is not None:
                return content

        raise ValueError(
            "stock research agent run did not return a final text response"
        )

    @staticmethod
    def _extract_message_content(message: Any) -> str | None:
        """Best-effort extraction of assistant message text across message shapes."""
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(message, Mapping):
            mapped_content = message.get("content")
            if isinstance(mapped_content, str) and mapped_content.strip():
                return mapped_content.strip()

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str) and item.strip():
                    text_parts.append(item.strip())
                    continue
                if isinstance(item, Mapping):
                    text_value = item.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        text_parts.append(text_value.strip())
            if text_parts:
                return "\n".join(text_parts)

        return None

    @staticmethod
    def _to_summary(report: StockResearchReport) -> StockResearchReportSummary:
        return StockResearchReportSummary(
            id=report.id,
            symbol=report.symbol,
            status=report.status,
            created_at=report.created_at,
            started_at=report.started_at,
            completed_at=report.completed_at,
            updated_at=report.updated_at,
        )

    @classmethod
    def _to_create_response(
        cls,
        report: StockResearchReport,
    ) -> StockResearchReportCreateResponse:
        summary = cls._to_summary(report)
        return StockResearchReportCreateResponse(**summary.model_dump())

    @classmethod
    def _to_detail_response(
        cls,
        report: StockResearchReport,
    ) -> StockResearchReportResponse:
        summary = cls._to_summary(report)
        return StockResearchReportResponse(
            **summary.model_dump(),
            content=report.content,
            sources=[
                StockResearchReportSourceResponse(
                    source_id=source.source_id,
                    url=source.url,
                    title=source.title,
                )
                for source in report.sources
            ],
            error=(
                None
                if report.error is None
                else StockResearchReportFailureResponse(
                    code=report.error.code,
                    message=report.error.message,
                )
            ),
        )
