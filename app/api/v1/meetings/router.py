"""Meeting management HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.api.deps import get_current_active_user
from app.common.service import get_meeting_management_service
from app.domain.models.user import User
from app.domain.schemas.meeting import (
    MeetingListQuery,
    MeetingListResponse,
    MeetingNoteChunkListResponse,
    MeetingPaginationParams,
    MeetingUpdateRequest,
    MeetingUpdateResponse,
    MeetingUtteranceListResponse,
)
from app.services.meeting.meeting_management_service import MeetingManagementService

router = APIRouter(prefix="/meetings", tags=["meetings"])

MeetingListQueryDep = Annotated[MeetingListQuery, Depends()]
MeetingPaginationDep = Annotated[MeetingPaginationParams, Depends()]
OrganizationHeader = Annotated[
    str | None,
    Header(alias="X-Organization-ID"),
]


@router.get("", response_model=MeetingListResponse)
async def list_meetings(
    query: MeetingListQueryDep,
    current_user: User = Depends(get_current_active_user),
    meeting_management_service: MeetingManagementService = Depends(
        get_meeting_management_service
    ),
    x_organization_id: OrganizationHeader = None,
) -> MeetingListResponse:
    """List the authenticated creator's meetings in the requested organization."""
    return await meeting_management_service.list_meetings(
        user_id=current_user.id,
        organization_id=x_organization_id,
        query=query,
    )


@router.patch("/{meeting_id}", response_model=MeetingUpdateResponse)
async def update_meeting(
    meeting_id: str,
    request: MeetingUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    meeting_management_service: MeetingManagementService = Depends(
        get_meeting_management_service
    ),
    x_organization_id: OrganizationHeader = None,
) -> MeetingUpdateResponse:
    """Update metadata or archive state for one owned meeting."""
    return await meeting_management_service.update_meeting(
        meeting_id=meeting_id,
        user_id=current_user.id,
        organization_id=x_organization_id,
        request=request,
    )


@router.get(
    "/{meeting_id}/utterances",
    response_model=MeetingUtteranceListResponse,
)
async def list_meeting_utterances(
    meeting_id: str,
    pagination: MeetingPaginationDep,
    current_user: User = Depends(get_current_active_user),
    meeting_management_service: MeetingManagementService = Depends(
        get_meeting_management_service
    ),
    x_organization_id: OrganizationHeader = None,
) -> MeetingUtteranceListResponse:
    """List persisted utterances for one owned meeting."""
    return await meeting_management_service.list_meeting_utterances(
        meeting_id=meeting_id,
        user_id=current_user.id,
        organization_id=x_organization_id,
        pagination=pagination,
    )


@router.get(
    "/{meeting_id}/note-chunks",
    response_model=MeetingNoteChunkListResponse,
)
async def list_meeting_note_chunks(
    meeting_id: str,
    pagination: MeetingPaginationDep,
    current_user: User = Depends(get_current_active_user),
    meeting_management_service: MeetingManagementService = Depends(
        get_meeting_management_service
    ),
    x_organization_id: OrganizationHeader = None,
) -> MeetingNoteChunkListResponse:
    """List raw persisted note chunks for one owned meeting."""
    return await meeting_management_service.list_meeting_note_chunks(
        meeting_id=meeting_id,
        user_id=current_user.id,
        organization_id=x_organization_id,
        pagination=pagination,
    )
