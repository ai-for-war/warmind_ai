"""Image model for uploaded image metadata storage."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Image(BaseModel):
    """Image domain model representing metadata stored in MongoDB."""

    id: str = Field(alias="_id")
    public_id: str
    organization_id: str
    uploaded_by: str
    original_filename: str
    mime_type: str
    size_bytes: int
    cloudinary_folder: str
    created_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
