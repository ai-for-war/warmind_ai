"""Health check endpoint for service monitoring."""

from fastapi import APIRouter

from app.domain.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check service health status.

    Returns:
        HealthResponse: Service health status.
    """
    return HealthResponse(status="healthy")
