"""Crawler service for Google Sheet data synchronization.

Handles syncing data from Google Sheets, applying column mappings,
and notifying users via WebSocket.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from app.domain.models.sheet_connection import SheetConnection, SheetSyncState
from app.domain.schemas.sheet_crawler import (
    SheetPreviewResponse,
    SyncStatus,
)
from app.infrastructure.google_sheets.client import (
    GoogleSheetClient,
    GoogleSheetClientError,
)
from app.repo.sheet_connection_repo import SheetConnectionRepository
from app.repo.sheet_data_repo import SheetDataRepository
from app.repo.sheet_sync_state_repo import SheetSyncStateRepository
from app.services.sheet_crawler.column_mapper import (
    ColumnMapper,
    MissingRequiredColumnError,
)
from app.common.event_socket import SheetSyncEvents
from app.socket_gateway.worker_gateway import worker_gateway

if TYPE_CHECKING:
    from app.services.analytics.cache_manager import AnalyticsCacheManager

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""

    success: bool
    rows_synced: int
    total_rows: int
    error_message: Optional[str] = None


class SheetCrawlerService:
    """Service for crawling and syncing Google Sheet data.

    Handles:
    - Fetching data from Google Sheets
    - Applying column mappings
    - Storing data in MongoDB
    - Updating sync state
    - Notifying users via WebSocket
    - Invalidating analytics cache after successful sync
    """

    def __init__(
        self,
        sheet_client: GoogleSheetClient,
        connection_repo: SheetConnectionRepository,
        sync_state_repo: SheetSyncStateRepository,
        data_repo: SheetDataRepository,
        cache_manager: Optional["AnalyticsCacheManager"] = None,
    ):
        """Initialize SheetCrawlerService.

        Args:
            sheet_client: Google Sheets API client
            connection_repo: Repository for sheet connections
            sync_state_repo: Repository for sync states
            data_repo: Repository for sheet raw data
            cache_manager: Optional analytics cache manager for invalidation
        """
        self.sheet_client = sheet_client
        self.connection_repo = connection_repo
        self.sync_state_repo = sync_state_repo
        self.data_repo = data_repo
        self.cache_manager = cache_manager
        self.column_mapper = ColumnMapper()

    async def _emit_sync_started(self, user_id: str, connection_id: str) -> None:
        """Emit sync started event via WebSocket.

        Args:
            user_id: User ID to notify
            connection_id: Connection ID being synced
        """
        await worker_gateway.emit_to_user(
            user_id=user_id,
            event=SheetSyncEvents.STARTED,
            data={"connection_id": connection_id},
        )

    async def _emit_sync_completed(
        self,
        user_id: str,
        connection_id: str,
        rows_synced: int,
        total_rows: int,
    ) -> None:
        """Emit sync completed event via WebSocket.

        Args:
            user_id: User ID to notify
            connection_id: Connection ID that was synced
            rows_synced: Number of rows synced in this operation
            total_rows: Total rows synced overall
        """
        await worker_gateway.emit_to_user(
            user_id=user_id,
            event=SheetSyncEvents.COMPLETED,
            data={
                "connection_id": connection_id,
                "rows_synced": rows_synced,
                "total_rows": total_rows,
            },
        )

    async def _emit_sync_failed(
        self,
        user_id: str,
        connection_id: str,
        error_message: str,
    ) -> None:
        """Emit sync failed event via WebSocket.

        Args:
            user_id: User ID to notify
            connection_id: Connection ID that failed
            error_message: Error description
        """
        await worker_gateway.emit_to_user(
            user_id=user_id,
            event=SheetSyncEvents.FAILED,
            data={
                "connection_id": connection_id,
                "error": error_message,
            },
        )

    async def sync_sheet(
        self,
        connection_id: str,
        user_id: Optional[str] = None,
    ) -> SyncResult:
        """Sync a single sheet connection.

        Performs incremental sync starting from last_synced_row + 1.

        Args:
            connection_id: ID of the connection to sync
            user_id: Optional user ID (fetched from connection if not provided)

        Returns:
            SyncResult with sync outcome details
        """
        # Get connection
        connection = await self.connection_repo.find_by_id(connection_id)
        if connection is None:
            return SyncResult(
                success=False,
                rows_synced=0,
                total_rows=0,
                error_message="Connection not found",
            )

        # Use provided user_id or get from connection
        effective_user_id = user_id or connection.user_id

        # Get current sync state
        sync_state = await self.sync_state_repo.find_by_connection_id(connection_id)
        last_synced_row = sync_state.last_synced_row if sync_state else 0
        total_rows_synced = sync_state.total_rows_synced if sync_state else 0

        # Notify sync started
        await self._emit_sync_started(effective_user_id, connection_id)

        # Update status to syncing
        await self.sync_state_repo.update_state(
            connection_id=connection_id,
            last_synced_row=last_synced_row,
            status=SyncStatus.SYNCING,
            total_rows_synced=total_rows_synced,
        )

        try:
            # Determine start row for sync
            # If never synced, start from data_start_row
            # Otherwise, start from last_synced_row + 1
            if last_synced_row == 0:
                start_row = connection.data_start_row
            else:
                start_row = last_synced_row + 1

            # Fetch headers first
            headers = await self.sheet_client.get_headers(
                sheet_id=connection.sheet_id,
                sheet_name=connection.sheet_name,
                header_row=connection.header_row,
            )

            # Validate required columns exist (Requirement 3.2)
            self.column_mapper.validate_required_columns(
                headers=headers,
                mappings=connection.column_mappings,
            )

            # Fetch data starting from start_row
            rows = await self.sheet_client.get_sheet_values(
                sheet_id=connection.sheet_id,
                sheet_name=connection.sheet_name,
                start_row=start_row,
            )

            # Process and store each row
            rows_synced = 0
            current_row_number = start_row

            for row in rows:
                # Skip empty rows
                if not any(cell.strip() for cell in row if cell):
                    current_row_number += 1
                    continue

                # Map row data using column mappings
                mapped_data = self.column_mapper.map_row(
                    row=row,
                    headers=headers,
                    mappings=connection.column_mappings,
                )

                # Get raw data with headers as keys
                raw_data = self.column_mapper.get_raw_data(row, headers)

                # Upsert to database
                await self.data_repo.upsert(
                    connection_id=connection_id,
                    row_number=current_row_number,
                    data=mapped_data,
                    raw_data=raw_data,
                )

                rows_synced += 1
                current_row_number += 1

            # Update sync state with success
            new_last_synced_row = (
                current_row_number - 1 if rows_synced > 0 else last_synced_row
            )
            new_total_rows = total_rows_synced + rows_synced

            await self.sync_state_repo.update_state(
                connection_id=connection_id,
                last_synced_row=new_last_synced_row,
                status=SyncStatus.SUCCESS,
                total_rows_synced=new_total_rows,
            )

            # Invalidate analytics cache after successful sync (Requirement 7.3)
            if self.cache_manager:
                try:
                    await self.cache_manager.invalidate(connection_id)
                    logger.debug(
                        "Invalidated analytics cache for connection %s",
                        connection_id,
                    )
                except Exception as e:
                    # Log but don't fail sync if cache invalidation fails
                    logger.warning(
                        "Failed to invalidate analytics cache for connection %s: %s",
                        connection_id,
                        e,
                    )

            # Notify sync completed
            await self._emit_sync_completed(
                user_id=effective_user_id,
                connection_id=connection_id,
                rows_synced=rows_synced,
                total_rows=new_total_rows,
            )

            logger.info(
                "Sync completed for connection %s: %s rows synced, %s total",
                connection_id,
                rows_synced,
                new_total_rows,
            )

            return SyncResult(
                success=True,
                rows_synced=rows_synced,
                total_rows=new_total_rows,
            )

        except GoogleSheetClientError as e:
            error_message = str(e)
            logger.error(
                "Sync failed for connection %s: %s", connection_id, error_message
            )

            # Update sync state with failure
            await self.sync_state_repo.update_state(
                connection_id=connection_id,
                last_synced_row=last_synced_row,
                status=SyncStatus.FAILED,
                total_rows_synced=total_rows_synced,
                error_message=error_message,
            )

            # Notify sync failed
            await self._emit_sync_failed(
                user_id=effective_user_id,
                connection_id=connection_id,
                error_message=error_message,
            )

            return SyncResult(
                success=False,
                rows_synced=0,
                total_rows=total_rows_synced,
                error_message=error_message,
            )

        except MissingRequiredColumnError as e:
            error_message = str(e)
            logger.error(
                "Sync failed for connection %s: %s", connection_id, error_message
            )

            # Update sync state with failure
            await self.sync_state_repo.update_state(
                connection_id=connection_id,
                last_synced_row=last_synced_row,
                status=SyncStatus.FAILED,
                total_rows_synced=total_rows_synced,
                error_message=error_message,
            )

            # Notify sync failed
            await self._emit_sync_failed(
                user_id=effective_user_id,
                connection_id=connection_id,
                error_message=error_message,
            )

            return SyncResult(
                success=False,
                rows_synced=0,
                total_rows=total_rows_synced,
                error_message=error_message,
            )

        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
            logger.exception("Sync failed for connection %s", connection_id)

            # Update sync state with failure
            await self.sync_state_repo.update_state(
                connection_id=connection_id,
                last_synced_row=last_synced_row,
                status=SyncStatus.FAILED,
                total_rows_synced=total_rows_synced,
                error_message=error_message,
            )

            # Notify sync failed
            await self._emit_sync_failed(
                user_id=effective_user_id,
                connection_id=connection_id,
                error_message=error_message,
            )

            return SyncResult(
                success=False,
                rows_synced=0,
                total_rows=total_rows_synced,
                error_message=error_message,
            )

    async def preview_sheet(
        self,
        connection_id: str,
        rows: int = 10,
    ) -> SheetPreviewResponse:
        """Fetch preview data from a sheet connection.

        Args:
            connection_id: ID of the connection to preview
            rows: Number of rows to preview (max 50)

        Returns:
            SheetPreviewResponse with headers and preview rows

        Raises:
            ValueError: If connection not found
            GoogleSheetClientError: If sheet access fails
        """
        # Get connection
        connection = await self.connection_repo.find_by_id(connection_id)
        if connection is None:
            raise ValueError("Connection not found")

        # Limit rows to max 50
        rows = min(rows, 50)

        # Fetch preview from Google Sheets
        preview_data = await self.sheet_client.get_preview(
            sheet_id=connection.sheet_id,
            sheet_name=connection.sheet_name,
            header_row=connection.header_row,
            data_start_row=connection.data_start_row,
            num_rows=rows,
        )

        return SheetPreviewResponse(
            headers=preview_data["headers"],
            rows=preview_data["rows"],
            total_rows=preview_data["total_rows"],
        )

    async def get_sync_state(
        self,
        connection_id: str,
    ) -> Optional[SheetSyncState]:
        """Get the current sync state for a connection.

        Args:
            connection_id: ID of the connection

        Returns:
            SheetSyncState if exists, None otherwise
        """
        return await self.sync_state_repo.find_by_connection_id(connection_id)

    async def get_connection(
        self,
        connection_id: str,
    ) -> Optional[SheetConnection]:
        """Get a connection by ID.

        Args:
            connection_id: ID of the connection

        Returns:
            SheetConnection if exists, None otherwise
        """
        return await self.connection_repo.find_by_id(connection_id)
