"""Image schemas for request/response validation."""

from datetime import datetime

from pydantic import BaseModel, Field


class ImageRecord(BaseModel):
    """Schema representing image metadata in API responses."""

    id: str
    public_id: str
    organization_id: str
    uploaded_by: str
    original_filename: str
    mime_type: str
    size_bytes: int
    cloudinary_folder: str
    created_at: datetime


class ImageUploadFailure(BaseModel):
    """Schema representing one failed file upload in a batch."""

    filename: str
    reason: str


class ImageUploadResponse(BaseModel):
    """Schema for batch image upload response."""

    uploaded: int
    failed: int
    images: list[ImageRecord]
    failures: list[ImageUploadFailure] = Field(default_factory=list)


class ImageDetailResponse(BaseModel):
    """Schema for image detail response including signed URL."""

    image: ImageRecord
    signed_url: str


class ImageListResponse(BaseModel):
    """Schema for paginated image list response."""

    items: list[ImageRecord]
    total: int
    skip: int
    limit: int
