"""Meeting transcript review API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.service import get_meeting_transcript_service
from app.domain.models.user import User
from app.domain.schemas.meeting_transcript import MeetingTranscriptPageResponse
from app.services.meeting.transcript_service import MeetingTranscriptService

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get(
    "/{meeting_id}/transcript",
    response_model=MeetingTranscriptPageResponse,
    status_code=status.HTTP_200_OK,
)
async def get_meeting_transcript(
    meeting_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    _: User = Depends(get_current_active_user),
    context: OrganizationContext = Depends(get_current_organization_context),
    transcript_service: MeetingTranscriptService = Depends(
        get_meeting_transcript_service
    ),
) -> MeetingTranscriptPageResponse:
    """Return a paginated saved transcript page. Requires `X-Organization-ID`."""
    try:
        return await transcript_service.get_transcript_page(
            meeting_id=meeting_id,
            organization_id=context.organization_id,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid transcript cursor",
        ) from exc
