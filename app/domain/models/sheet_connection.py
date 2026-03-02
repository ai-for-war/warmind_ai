"""Domain models for Google Sheet Crawler feature (DB models only)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.schemas.sheet_crawler import ColumnMapping, SyncStatus


class SheetConnection(BaseModel):
    """Connection configuration between the system and a Google Sheet."""

    id: str = Field(alias="_id")
    user_id: str
    organization_id: Optional[str] = None
    sheet_id: str
    sheet_name: str = "Sheet1"
    column_mappings: list[ColumnMapping]
    header_row: int = 1
    data_start_row: int = 2
    sync_enabled: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        use_enum_values = True


class SheetSyncState(BaseModel):
    """Sync state tracking for a sheet connection."""

    id: str = Field(alias="_id")
    connection_id: str
    last_synced_row: int = 0
    last_sync_time: Optional[datetime] = None
    status: SyncStatus = SyncStatus.PENDING
    error_message: Optional[str] = None
    total_rows_synced: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        use_enum_values = True


class SheetRawData(BaseModel):
    """Raw data crawled from Google Sheet and stored in database."""

    id: str = Field(alias="_id")
    connection_id: str
    row_number: int
    data: dict  # Mapped data
    raw_data: dict  # Original row
    synced_at: datetime

    class Config:
        populate_by_name = True
