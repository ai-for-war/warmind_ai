"""Application service for authenticated meeting management APIs."""

from __future__ import annotations

import asyncio

from app.common.exceptions import (
    AppException,
    InvalidMeetingUpdateError,
    MeetingNotFoundError,
    PermissionDeniedError,
)
from app.domain.models.meeting import Meeting
from app.domain.models.meeting_note_chunk import MeetingNoteChunk
from app.domain.models.meeting_utterance import MeetingUtterance
from app.domain.schemas.meeting import (
    MeetingListQuery,
    MeetingListResponse,
    MeetingNoteChunkListResponse,
    MeetingNoteChunkRecord,
    MeetingPaginationParams,
    MeetingSummaryRecord,
    MeetingUpdateRequest,
    MeetingUpdateResponse,
    MeetingUtteranceListResponse,
    MeetingUtteranceRecord,
)
from app.repo.meeting_note_chunk_repo import MeetingNoteChunkRepository
from app.repo.meeting_repo import MeetingRepository
from app.repo.meeting_utterance_repo import MeetingUtteranceRepository
from app.repo.organization_member_repo import OrganizationMemberRepository


class MeetingManagementService:
    """Coordinate creator-scoped meeting history reads and updates."""

    def __init__(
        self,
        *,
        meeting_repo: MeetingRepository,
        utterance_repo: MeetingUtteranceRepository,
        note_chunk_repo: MeetingNoteChunkRepository,
        member_repo: OrganizationMemberRepository,
    ) -> None:
        self.meeting_repo = meeting_repo
        self.utterance_repo = utterance_repo
        self.note_chunk_repo = note_chunk_repo
        self.member_repo = member_repo

    async def list_meetings(
        self,
        *,
        user_id: str,
        organization_id: str | None,
        query: MeetingListQuery,
    ) -> MeetingListResponse:
        """List one creator's meetings within the active organization scope."""
        organization_id = await self._ensure_active_membership(
            user_id=user_id,
            organization_id=organization_id,
        )
        items, total = await asyncio.gather(
            self.meeting_repo.list_for_creator(
                organization_id=organization_id,
                created_by=user_id,
                scope=query.scope,
                status=query.status,
                started_at_from=query.started_at_from,
                started_at_to=query.started_at_to,
                q=query.q,
                skip=query.skip,
                limit=query.limit,
            ),
            self.meeting_repo.count_for_creator(
                organization_id=organization_id,
                created_by=user_id,
                scope=query.scope,
                status=query.status,
                started_at_from=query.started_at_from,
                started_at_to=query.started_at_to,
                q=query.q,
            ),
        )
        return MeetingListResponse(
            items=[self._to_meeting_summary(item) for item in items],
            total=total,
            skip=query.skip,
            limit=query.limit,
        )

    async def update_meeting(
        self,
        *,
        meeting_id: str,
        user_id: str,
        organization_id: str | None,
        request: MeetingUpdateRequest,
    ) -> MeetingUpdateResponse:
        """Update one owned meeting's metadata or archive state."""
        organization_id = await self._ensure_active_membership(
            user_id=user_id,
            organization_id=organization_id,
        )
        self._ensure_update_requested(request)

        updated = await self.meeting_repo.update_metadata_for_creator(
            meeting_id=meeting_id,
            organization_id=organization_id,
            created_by=user_id,
            title=request.title if "title" in request.model_fields_set else None,
            source=request.source if "source" in request.model_fields_set else None,
            archived=(
                request.archived if "archived" in request.model_fields_set else None
            ),
            archived_by=user_id if request.archived is True else None,
        )
        if updated is None:
            raise MeetingNotFoundError()

        return MeetingUpdateResponse(meeting=self._to_meeting_summary(updated))

    async def list_meeting_utterances(
        self,
        *,
        meeting_id: str,
        user_id: str,
        organization_id: str | None,
        pagination: MeetingPaginationParams,
    ) -> MeetingUtteranceListResponse:
        """List persisted utterances for one owned meeting."""
        meeting = await self._get_owned_meeting(
            meeting_id=meeting_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        items, total = await asyncio.gather(
            self.utterance_repo.list_by_meeting_paginated(
                meeting_id=meeting.id,
                skip=pagination.skip,
                limit=pagination.limit,
            ),
            self.utterance_repo.count_by_meeting(meeting_id=meeting.id),
        )
        return MeetingUtteranceListResponse(
            items=[self._to_utterance_record(item) for item in items],
            total=total,
            skip=pagination.skip,
            limit=pagination.limit,
        )

    async def list_meeting_note_chunks(
        self,
        *,
        meeting_id: str,
        user_id: str,
        organization_id: str | None,
        pagination: MeetingPaginationParams,
    ) -> MeetingNoteChunkListResponse:
        """List raw persisted note chunks for one owned meeting."""
        meeting = await self._get_owned_meeting(
            meeting_id=meeting_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        items, total = await asyncio.gather(
            self.note_chunk_repo.list_by_meeting_paginated(
                meeting_id=meeting.id,
                skip=pagination.skip,
                limit=pagination.limit,
            ),
            self.note_chunk_repo.count_by_meeting(meeting_id=meeting.id),
        )
        return MeetingNoteChunkListResponse(
            items=[self._to_note_chunk_record(item) for item in items],
            total=total,
            skip=pagination.skip,
            limit=pagination.limit,
        )

    async def _get_owned_meeting(
        self,
        *,
        meeting_id: str,
        user_id: str,
        organization_id: str | None,
    ) -> Meeting:
        """Return one owned meeting after membership validation."""
        normalized_organization_id = await self._ensure_active_membership(
            user_id=user_id,
            organization_id=organization_id,
        )
        meeting = await self.meeting_repo.get_for_creator(
            meeting_id=meeting_id,
            organization_id=normalized_organization_id,
            created_by=user_id,
        )
        if meeting is None:
            raise MeetingNotFoundError()
        return meeting

    async def _ensure_active_membership(
        self,
        *,
        user_id: str,
        organization_id: str | None,
    ) -> str:
        """Require a non-empty organization header and active membership."""
        normalized_organization_id = (organization_id or "").strip()
        if not normalized_organization_id:
            raise AppException("X-Organization-ID header is required")

        membership = await self.member_repo.find_by_user_and_org(
            user_id=user_id,
            organization_id=normalized_organization_id,
            is_active=True,
        )
        if membership is None:
            raise PermissionDeniedError(
                "Meeting management requires an active membership in the requested organization"
            )
        return normalized_organization_id

    @staticmethod
    def _ensure_update_requested(request: MeetingUpdateRequest) -> None:
        """Reject empty PATCH payloads, including model-constructed instances."""
        if request.title is None and request.source is None and request.archived is None:
            raise InvalidMeetingUpdateError()

    @staticmethod
    def _to_meeting_summary(meeting: Meeting) -> MeetingSummaryRecord:
        """Convert one durable meeting model into the API summary schema."""
        return MeetingSummaryRecord(
            id=meeting.id,
            title=meeting.title,
            source=meeting.source,
            status=meeting.status,
            started_at=meeting.started_at,
            ended_at=meeting.ended_at,
            archived_at=meeting.archived_at,
            archived_by=meeting.archived_by,
        )

    @staticmethod
    def _to_utterance_record(utterance: MeetingUtterance) -> MeetingUtteranceRecord:
        """Convert one durable utterance model into the API schema."""
        return MeetingUtteranceRecord.model_validate(
            utterance.model_dump(mode="python")
        )

    @staticmethod
    def _to_note_chunk_record(note_chunk: MeetingNoteChunk) -> MeetingNoteChunkRecord:
        """Convert one durable note chunk model into the API schema."""
        return MeetingNoteChunkRecord.model_validate(
            note_chunk.model_dump(mode="python")
        )
