"""Image model for uploaded/generated image metadata storage."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ImageSource(str, Enum):
    """Image asset source."""

    UPLOAD = "upload"
    GENERATION = "generation"


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
    source: ImageSource = ImageSource.UPLOAD
    generation_job_id: Optional[str] = None
    provider: Optional[str] = None
    provider_model: Optional[str] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        use_enum_values = True
