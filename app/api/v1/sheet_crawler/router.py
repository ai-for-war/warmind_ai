"""Sheet Crawler public API router.

Provides endpoints for managing Google Sheet connections,
triggering syncs, and retrieving synced data.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.repo import (
    get_sheet_connection_repo,
    get_sheet_data_repo,
    get_sheet_sync_state_repo,
)
from app.common.service import (
    get_crawler_service,
    get_google_sheet_client,
    get_redis_queue,
)
from app.config.settings import get_settings
from app.domain.models.user import User
from app.domain.schemas.sheet_crawler import (
    ConnectionResponse,
    CreateConnectionRequest,
    ServiceAccountInfoResponse,
    SheetDataResponse,
    SheetPreviewResponse,
    SyncStatus,
    SyncStatusResponse,
    UpdateConnectionRequest,
)
from app.infrastructure.google_sheets.client import GoogleSheetClientError
from app.infrastructure.redis.redis_queue import RedisQueue
from app.repo.sheet_connection_repo import SheetConnectionRepository
from app.repo.sheet_data_repo import SheetDataRepository
from app.repo.sheet_sync_state_repo import SheetSyncStateRepository
from app.services.sheet_crawler.crawler_service import SheetCrawlerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sheet-connections", tags=["sheet-crawler"])


@router.get("/service-account", response_model=ServiceAccountInfoResponse)
async def get_service_account_info(
    _: User = Depends(get_current_active_user),
    __: OrganizationContext = Depends(get_current_organization_context),
) -> ServiceAccountInfoResponse:
    """Get service account information for sharing Google Sheets.

    Returns the service account email and instructions for sharing.

    Returns:
        ServiceAccountInfoResponse with email and instructions
    """
    settings = get_settings()
    return ServiceAccountInfoResponse(
        email=settings.GOOGLE_SERVICE_ACCOUNT_EMAIL,
        instructions=(
            "To connect your Google Sheet, share it with the email address above. "
            "Grant 'Viewer' access for read-only sync, or 'Editor' access if you "
            "need write capabilities in the future."
        ),
    )


# Connection CRUD endpoints


@router.post("", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    request: CreateConnectionRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
    sheet_client=Depends(get_google_sheet_client),
    queue: RedisQueue = Depends(get_redis_queue),
) -> ConnectionResponse:
    """Create a new sheet connection.

    Validates that the service account can access the sheet before creating.

    Args:
        request: Connection creation request
        current_user: Authenticated user
        connection_repo: Sheet connection repository
        sheet_client: Google Sheet client

    Returns:
        Created connection details

    Raises:
        HTTPException: 400 if sheet is not accessible
    """
    # Verify sheet access
    try:
        has_access = await sheet_client.check_access(request.sheet_id)
        if not has_access:
            settings = get_settings()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot access sheet. Please share with {settings.GOOGLE_SERVICE_ACCOUNT_EMAIL}",
            )
    except GoogleSheetClientError as e:
        settings = get_settings()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot access sheet. Please share with {settings.GOOGLE_SERVICE_ACCOUNT_EMAIL}. Error: {str(e)}",
        ) from e

    # Create connection
    connection = await connection_repo.create(
        current_user.id,
        request,
        organization_id=org_context.organization_id,
    )

    # Trigger initial sync by enqueuing task to Redis queue
    settings = get_settings()
    task_data = {
        "connection_id": connection.id,
        "user_id": current_user.id,
        "organization_id": org_context.organization_id,
        "retry_count": 0,
    }
    await queue.enqueue(settings.SHEET_SYNC_QUEUE_NAME, task_data)

    logger.info(
        "Created connection %s and enqueued initial sync task",
        connection.id,
    )

    return ConnectionResponse(
        id=connection.id,
        sheet_id=connection.sheet_id,
        sheet_name=connection.sheet_name,
        column_mappings=connection.column_mappings,
        sync_enabled=connection.sync_enabled,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.get("", response_model=list[ConnectionResponse])
async def list_connections(
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
) -> list[ConnectionResponse]:
    """List all sheet connections for the current user.

    Args:
        current_user: Authenticated user
        connection_repo: Sheet connection repository

    Returns:
        List of connection details
    """
    connections = await connection_repo.find_by_user_id(
        current_user.id,
        organization_id=org_context.organization_id,
    )

    return [
        ConnectionResponse(
            id=conn.id,
            sheet_id=conn.sheet_id,
            sheet_name=conn.sheet_name,
            column_mappings=conn.column_mappings,
            sync_enabled=conn.sync_enabled,
            created_at=conn.created_at,
            updated_at=conn.updated_at,
        )
        for conn in connections
    ]


@router.get("/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
) -> ConnectionResponse:
    """Get a specific sheet connection by ID.

    Args:
        connection_id: Connection ID
        current_user: Authenticated user
        connection_repo: Sheet connection repository

    Returns:
        Connection details

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
    """
    connection = await connection_repo.find_by_id(
        connection_id,
        organization_id=org_context.organization_id,
    )

    if connection is None or connection.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    return ConnectionResponse(
        id=connection.id,
        sheet_id=connection.sheet_id,
        sheet_name=connection.sheet_name,
        column_mappings=connection.column_mappings,
        sync_enabled=connection.sync_enabled,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.put("/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: str,
    request: UpdateConnectionRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
) -> ConnectionResponse:
    """Update a sheet connection.

    Args:
        connection_id: Connection ID
        request: Update request
        current_user: Authenticated user
        connection_repo: Sheet connection repository

    Returns:
        Updated connection details

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
    """
    # Verify ownership first
    existing = await connection_repo.find_by_id(
        connection_id,
        organization_id=org_context.organization_id,
    )
    if existing is None or existing.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Update connection
    connection = await connection_repo.update(
        connection_id,
        request,
        organization_id=org_context.organization_id,
    )

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    return ConnectionResponse(
        id=connection.id,
        sheet_id=connection.sheet_id,
        sheet_name=connection.sheet_name,
        column_mappings=connection.column_mappings,
        sync_enabled=connection.sync_enabled,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
    sync_state_repo: SheetSyncStateRepository = Depends(get_sheet_sync_state_repo),
    data_repo: SheetDataRepository = Depends(get_sheet_data_repo),
) -> None:
    """Delete a sheet connection and all associated data.

    Cascade deletes sync state and raw data.

    Args:
        connection_id: Connection ID
        current_user: Authenticated user
        connection_repo: Sheet connection repository
        sync_state_repo: Sync state repository
        data_repo: Sheet data repository

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
    """
    # Verify ownership first
    existing = await connection_repo.find_by_id(
        connection_id,
        organization_id=org_context.organization_id,
    )
    if existing is None or existing.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Cascade delete: sync state and raw data
    await sync_state_repo.delete_by_connection_id(connection_id)
    await data_repo.delete_by_connection_id(connection_id)

    # Delete connection
    await connection_repo.delete(
        connection_id,
        organization_id=org_context.organization_id,
    )


# Sync operations


@router.post("/{connection_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    connection_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
    queue: RedisQueue = Depends(get_redis_queue),
) -> dict:
    """Trigger a manual sync for a connection.

    Enqueues a sync task and returns immediately.

    Args:
        connection_id: Connection ID
        current_user: Authenticated user
        connection_repo: Sheet connection repository
        queue: Redis queue instance

    Returns:
        Accepted response with connection_id

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
    """
    # Verify ownership
    connection = await connection_repo.find_by_id(
        connection_id,
        organization_id=org_context.organization_id,
    )
    if connection is None or connection.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Enqueue sync task
    settings = get_settings()
    task_data = {
        "connection_id": connection_id,
        "user_id": current_user.id,
        "organization_id": org_context.organization_id,
        "retry_count": 0,
    }
    await queue.enqueue(settings.SHEET_SYNC_QUEUE_NAME, task_data)

    return {
        "status": "accepted",
        "connection_id": connection_id,
        "message": "Sync task enqueued",
    }


@router.get("/{connection_id}/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(
    connection_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
    sync_state_repo: SheetSyncStateRepository = Depends(get_sheet_sync_state_repo),
) -> SyncStatusResponse:
    """Get the sync status for a connection.

    Args:
        connection_id: Connection ID
        current_user: Authenticated user
        connection_repo: Sheet connection repository
        sync_state_repo: Sync state repository

    Returns:
        Current sync status

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
    """
    # Verify ownership
    connection = await connection_repo.find_by_id(
        connection_id,
        organization_id=org_context.organization_id,
    )
    if connection is None or connection.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Get sync state
    sync_state = await sync_state_repo.find_by_connection_id(connection_id)

    if sync_state is None:
        # No sync has been performed yet
        return SyncStatusResponse(
            connection_id=connection_id,
            status=SyncStatus.PENDING,
            last_synced_row=0,
            last_sync_time=None,
            total_rows_synced=0,
            error_message=None,
        )

    return SyncStatusResponse(
        connection_id=connection_id,
        status=sync_state.status,
        last_synced_row=sync_state.last_synced_row,
        last_sync_time=sync_state.last_sync_time,
        total_rows_synced=sync_state.total_rows_synced,
        error_message=sync_state.error_message,
    )


# Data operations


@router.get("/{connection_id}/preview", response_model=SheetPreviewResponse)
async def preview_sheet(
    connection_id: str,
    rows: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
    crawler_service: SheetCrawlerService = Depends(get_crawler_service),
) -> SheetPreviewResponse:
    """Preview data from a Google Sheet.

    Fetches headers and sample rows without syncing.

    Args:
        connection_id: Connection ID
        rows: Number of rows to preview (1-50)
        current_user: Authenticated user
        connection_repo: Sheet connection repository
        crawler_service: Crawler service

    Returns:
        Preview data with headers and rows

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
        HTTPException: 400 if sheet is not accessible
    """
    # Verify ownership
    connection = await connection_repo.find_by_id(
        connection_id,
        organization_id=org_context.organization_id,
    )
    if connection is None or connection.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    try:
        preview = await crawler_service.preview_sheet(connection_id, rows)
        return preview
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except GoogleSheetClientError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot access sheet: {str(e)}",
        ) from e


@router.get("/{connection_id}/data", response_model=SheetDataResponse)
async def get_synced_data(
    connection_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    connection_repo: SheetConnectionRepository = Depends(get_sheet_connection_repo),
    data_repo: SheetDataRepository = Depends(get_sheet_data_repo),
) -> SheetDataResponse:
    """Get synced data for a connection with pagination.

    Args:
        connection_id: Connection ID
        page: Page number (1-indexed)
        page_size: Number of records per page (1-100)
        current_user: Authenticated user
        connection_repo: Sheet connection repository
        data_repo: Sheet data repository

    Returns:
        Paginated synced data

    Raises:
        HTTPException: 404 if connection not found or belongs to another user
    """
    # Verify ownership
    connection = await connection_repo.find_by_id(
        connection_id,
        organization_id=org_context.organization_id,
    )
    if connection is None or connection.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    # Get paginated data
    data_list, total = await data_repo.find_by_connection_id(
        connection_id=connection_id,
        page=page,
        page_size=page_size,
    )

    return SheetDataResponse(
        data=[item.data for item in data_list],
        total=total,
        page=page,
        page_size=page_size,
    )
