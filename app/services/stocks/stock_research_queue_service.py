"""Queue helper for stock research report execution tasks."""

from __future__ import annotations

from app.domain.models.stock_research_report import (
    StockResearchReport,
    StockResearchReportRuntimeConfig,
)
from app.domain.schemas.stock_research_report import (
    StockResearchReportRuntimeConfigResponse,
)
from app.domain.schemas.stock_research_task import StockResearchTask
from app.infrastructure.redis.redis_queue import RedisQueue
from app.agents.implementations.stock_research_agent.runtime import (
    StockResearchAgentRuntimeConfig,
)

DEFAULT_STOCK_RESEARCH_QUEUE_NAME = "stock_research_tasks"


class StockResearchQueueService:
    """Build and enqueue stock research worker task payloads."""

    def __init__(
        self,
        *,
        queue: RedisQueue,
        queue_name: str = DEFAULT_STOCK_RESEARCH_QUEUE_NAME,
    ) -> None:
        self.queue = queue
        self.queue_name = queue_name

    async def enqueue_report(
        self,
        *,
        report_id: str,
        symbol: str,
        runtime_config: StockResearchReportRuntimeConfig
        | StockResearchAgentRuntimeConfig
        | StockResearchReportRuntimeConfigResponse,
    ) -> bool:
        """Enqueue one persisted stock research report for worker execution."""
        task = StockResearchTask(
            report_id=report_id,
            symbol=symbol,
            runtime_config=StockResearchReportRuntimeConfigResponse(
                provider=runtime_config.provider,
                model=runtime_config.model,
                reasoning=runtime_config.reasoning,
            ),
        )
        return await self.queue.enqueue(
            self.queue_name,
            task.model_dump(mode="json", exclude_none=True),
        )

    async def enqueue_report_model(self, report: StockResearchReport) -> bool:
        """Enqueue one stock research report model."""
        if report.id is None or report.runtime_config is None:
            return False
        return await self.enqueue_report(
            report_id=report.id,
            symbol=report.symbol,
            runtime_config=report.runtime_config,
        )
