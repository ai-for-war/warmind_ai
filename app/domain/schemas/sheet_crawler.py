"""API schemas for Google Sheet Crawler feature."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SyncStatus(str, Enum):
    """Sync status for sheet connections."""

    PENDING = "pending"
    SYNCING = "syncing"
    SUCCESS = "success"
    FAILED = "failed"


class ColumnMapping(BaseModel):
    """Mapping between Google Sheet columns and system fields."""

    system_field: str  # e.g., "product_name"
    sheet_column: str  # e.g., "A" or "Product Name"
    data_type: str = "string"  # string, number, integer, date
    required: bool = False


# Request Schemas
class CreateConnectionRequest(BaseModel):
    """Schema for creating a new sheet connection."""

    sheet_id: str
    sheet_name: str = "Sheet1"
    column_mappings: list[ColumnMapping]
    header_row: int = Field(default=1, ge=1)
    data_start_row: int = Field(default=2, ge=1)


class UpdateConnectionRequest(BaseModel):
    """Schema for updating an existing sheet connection."""

    sheet_name: Optional[str] = None
    column_mappings: Optional[list[ColumnMapping]] = None
    sync_enabled: Optional[bool] = None


# Response Schemas
class ConnectionResponse(BaseModel):
    """Schema for sheet connection response."""

    id: str
    sheet_id: str
    sheet_name: str
    column_mappings: list[ColumnMapping]
    sync_enabled: bool
    created_at: datetime
    updated_at: datetime


class SyncStatusResponse(BaseModel):
    """Schema for sync status response."""

    connection_id: str
    status: SyncStatus
    last_synced_row: int
    last_sync_time: Optional[datetime]
    total_rows_synced: int
    error_message: Optional[str]


class SheetPreviewResponse(BaseModel):
    """Schema for sheet preview response."""

    headers: list[str]
    rows: list[dict]
    total_rows: int


class SheetDataResponse(BaseModel):
    """Schema for paginated sheet data response."""

    data: list[dict]
    total: int
    page: int
    page_size: int


class ServiceAccountInfoResponse(BaseModel):
    """Schema for service account information response."""

    email: str
    instructions: str
