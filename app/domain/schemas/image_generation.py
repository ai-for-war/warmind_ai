"""Request/response schemas for text-to-image generation jobs."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ImageGenerationAspectRatio(str, Enum):
    """Supported MiniMax text-to-image aspect ratios."""

    RATIO_1_1 = "1:1"
    RATIO_16_9 = "16:9"
    RATIO_4_3 = "4:3"
    RATIO_3_2 = "3:2"
    RATIO_2_3 = "2:3"
    RATIO_3_4 = "3:4"
    RATIO_9_16 = "9:16"
    RATIO_21_9 = "21:9"


class ImageGenerationJobStatus(str, Enum):
    """Canonical API-visible status values for generation jobs."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CreateTextToImageJobRequest(BaseModel):
    """Schema for creating a text-to-image generation job."""

    prompt: str = Field(..., min_length=1, max_length=1500)
    aspect_ratio: ImageGenerationAspectRatio
    seed: Optional[int] = Field(default=None, ge=0, le=2147483647)
    prompt_optimizer: bool = False

    class Config:
        use_enum_values = True


class TextToImageGenerationJobRecord(BaseModel):
    """Authoritative persisted job representation returned by APIs."""

    id: str
    organization_id: str
    created_by: str
    type: str = "text_to_image"
    provider: str = "minimax"
    provider_model: str = "image-01"
    status: ImageGenerationJobStatus
    prompt: str
    aspect_ratio: ImageGenerationAspectRatio
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

    class Config:
        use_enum_values = True


class CreateTextToImageJobResponse(BaseModel):
    """Schema for create-job response."""

    job_id: str
    status: ImageGenerationJobStatus = ImageGenerationJobStatus.PENDING

    class Config:
        use_enum_values = True


class ImageGenerationOutputImageAccess(BaseModel):
    """Output image access data for detail responses."""

    image_id: str
    signed_url: str


class ImageGenerationJobDetailResponse(BaseModel):
    """Schema for generation job detail response."""

    job: TextToImageGenerationJobRecord
    output_images: list[ImageGenerationOutputImageAccess] = Field(default_factory=list)


class ImageGenerationJobSummaryItem(BaseModel):
    """Schema for generation job summary in history list."""

    id: str
    status: ImageGenerationJobStatus
    prompt: str
    aspect_ratio: ImageGenerationAspectRatio
    requested_at: datetime
    completed_at: Optional[datetime] = None
    output_image_ids: list[str] = Field(default_factory=list)
    success_count: int = 0
    failed_count: int = 0

    class Config:
        use_enum_values = True


class ImageGenerationHistoryResponse(BaseModel):
    """Schema for paginated generation history response."""

    items: list[ImageGenerationJobSummaryItem]
    total: int
    skip: int
    limit: int


class CancelImageGenerationJobResponse(BaseModel):
    """Schema for cancel-job response."""

    job_id: str
    status: ImageGenerationJobStatus = ImageGenerationJobStatus.CANCELLED
    cancelled_at: datetime

    class Config:
        use_enum_values = True


class ImageGenerationLifecycleEventPayload(BaseModel):
    """Shared lifecycle payload shape for socket emission contracts."""

    job_id: str
    organization_id: str
    status: ImageGenerationJobStatus
    requested_count: int = 1
    success_count: int = 0
    failed_count: int = 0
    image_ids: list[str] = Field(default_factory=list)
    error_message: Optional[str] = None

    class Config:
        use_enum_values = True
