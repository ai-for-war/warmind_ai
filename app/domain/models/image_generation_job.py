"""Image generation job domain model and enums."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ImageGenerationJobType(str, Enum):
    """Supported generation job types."""

    TEXT_TO_IMAGE = "text_to_image"


class ImageGenerationProvider(str, Enum):
    """Supported generation providers."""

    MINIMAX = "minimax"


class ImageGenerationJobStatus(str, Enum):
    """Lifecycle status for image generation jobs."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImageGenerationJob(BaseModel):
    """Persisted image generation job document in MongoDB."""

    id: str = Field(alias="_id")
    organization_id: str
    created_by: str
    type: ImageGenerationJobType = ImageGenerationJobType.TEXT_TO_IMAGE
    provider: ImageGenerationProvider = ImageGenerationProvider.MINIMAX
    provider_model: str = "image-01"
    status: ImageGenerationJobStatus = ImageGenerationJobStatus.PENDING
    prompt: str
    aspect_ratio: str
    seed: Optional[int] = None
    prompt_optimizer: bool = False
    requested_count: int = 1
    retry_count: int = 0
    provider_trace_id: Optional[str] = None
    output_image_ids: list[str] = Field(default_factory=list)
    success_count: int = 0
    failed_count: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    requested_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        use_enum_values = True
