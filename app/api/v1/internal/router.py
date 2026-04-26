"""Internal API router for system-to-system communication.

This router handles endpoints called by Cloud Scheduler and other
internal services. All endpoints require API key authentication.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.common.repo import get_sheet_connection_repo
from app.common.service import (
    get_redis_queue,
    get_stock_research_schedule_dispatcher_service,
)
from app.config.settings import get_settings
from app.infrastructure.redis.redis_queue import RedisQueue
from app.repo.sheet_connection_repo import SheetConnectionRepository
from app.services.stocks.stock_research_schedule_dispatcher_service import (
    StockResearchScheduleDispatcherService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_internal_api_key(
    api_key: str | None = Depends(api_key_header),
) -> bool:
    """Verify the internal API key.

    Args:
        api_key: API key from X-API-Key header

    Returns:
        True if valid

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    settings = get_settings()
    if api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return True


async def enqueue_all_connections(
    connection_repo: SheetConnectionRepository,
    queue: RedisQueue,
) -> None:
    """Background task to enqueue sync tasks for all enabled connections.

    Args:
        connection_repo: Repository for sheet connections
        queue: Redis queue instance
    """
    try:
        settings = get_settings()

        # Get all enabled connections
        connections = await connection_repo.find_all_enabled()
        logger.info("Found %d enabled connections to sync", len(connections))

        # Enqueue each connection
        enqueued_count = 0
        for connection in connections:
            task_data = {
                "connection_id": connection.id,
                "user_id": connection.user_id,
                "retry_count": 0,
            }
            success = await queue.enqueue(settings.SHEET_SYNC_QUEUE_NAME, task_data)
            if success:
                enqueued_count += 1

        logger.info(
            "Enqueued %d/%d sync tasks",
            enqueued_count,
            len(connections),
        )

    except Exception as e:
        logger.exception("Failed to enqueue connections: %s", e)


async def dispatch_stock_research_schedules(
    dispatcher: StockResearchScheduleDispatcherService,
) -> None:
    """Background task to dispatch due stock research schedules."""
    try:
        result = await dispatcher.dispatch_due()
        logger.info(
            "Dispatched stock research schedules scanned=%d dispatched=%d "
            "skipped=%d enqueue_failed=%d",
            result.scanned,
            result.dispatched,
            result.skipped,
            result.enqueue_failed,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to dispatch stock research schedules: %s", exc)


@router.post("/trigger-sync")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_internal_api_key),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
    queue: RedisQueue = Depends(get_redis_queue),
) -> dict:
    """Trigger sync for all enabled sheet connections.

    Called by Cloud Scheduler every 5 minutes.
    Returns immediately and enqueues tasks in background.

    Args:
        background_tasks: FastAPI background tasks
        _: API key verification dependency
        connection_repo: Sheet connection repository
        queue: Redis queue instance

    Returns:
        Accepted response with timestamp
    """
    background_tasks.add_task(enqueue_all_connections, connection_repo, queue)

    return {
        "status": "accepted",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/trigger-stock-research-schedules")
async def trigger_stock_research_schedules(
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_internal_api_key),
    dispatcher: StockResearchScheduleDispatcherService = Depends(
        get_stock_research_schedule_dispatcher_service
    ),
) -> dict[str, object]:
    """Trigger dispatch for due stock research schedules.

    Called by EventBridge Scheduler every 15 minutes.
    """
    background_tasks.add_task(dispatch_stock_research_schedules, dispatcher)
    return {
        "status": "accepted",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
